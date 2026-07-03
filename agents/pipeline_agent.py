"""DataPipelineAgent — nightly ingest from USGS / U.S. Drought Monitor / U.S. Census into PostGIS.

Runs unattended (no approval needed — it only writes to our own DB, takes no
external action). Each source is isolated so one failing API doesn't abort the
whole refresh.
"""
from __future__ import annotations

from django.utils import timezone

from core.models import RawDataRecord, Watershed
from integrations import demographics, drought, usgs
from .base import BaseAgent


class DataPipelineAgent(BaseAgent):
    name = "data_pipeline"

    def run(self) -> dict:
        watersheds = list(Watershed.objects.all())
        self.log("pipeline_started", watersheds=len(watersheds))

        ingested = 0
        errors: list[str] = []

        for ws in watersheds:
            ingested += self._ingest_source("usgs", ws, errors)
            ingested += self._ingest_source("drought", ws, errors)
            ingested += self._ingest_source("demographics", ws, errors)

        self.log("pipeline_finished", ingested=ingested, errors=len(errors))
        return {"ingested": ingested, "errors": errors, "at": timezone.now().isoformat()}

    def _ingest_source(self, source: str, ws: Watershed, errors: list[str]) -> int:
        try:
            if source == "usgs":
                rows = self._fetch_usgs(ws)
                src = RawDataRecord.Source.USGS
            elif source == "drought":
                rows = self._fetch_drought(ws)
                src = RawDataRecord.Source.USDM
            else:  # demographics
                rows = self._fetch_demographics(ws)
                src = RawDataRecord.Source.CENSUS
        except Exception as exc:  # noqa: BLE001 - isolate per-source failures
            errors.append(f"{source}:{ws.huc_code}:{exc}")
            self.log("source_failed", source=source, huc=ws.huc_code, error=str(exc))
            return 0

        objs = [
            RawDataRecord(
                source=src,
                watershed=ws,
                metric=r["metric"],
                value=r["value"],
                unit=r.get("unit", ""),
                observed_at=r["observed_at"],
                raw=r.get("raw", {}),
            )
            for r in rows
        ]
        RawDataRecord.objects.bulk_create(objs, batch_size=500)
        return len(objs)

    def _fetch_usgs(self, ws: Watershed) -> list[dict]:
        """Current flow + today's historical median for the watershed's gauge.

        If the watershed has a specific USGS site number we get a precise gauge
        reading plus the day-of-year median baseline. Otherwise we fall back to
        a broad HUC query (flow only, no baseline).
        """
        if not ws.usgs_site_no:
            return usgs.fetch_streamflow(ws.huc_code)

        rows = usgs.fetch_latest_by_sites([ws.usgs_site_no])
        median = usgs.median_for_date(ws.usgs_site_no)
        if median is not None:
            rows.append(
                {
                    "metric": "streamflow_median_cfs",
                    "value": median,
                    "unit": "ft3/s",
                    "observed_at": timezone.now(),
                    "raw": {"site_no": ws.usgs_site_no, "stat": "p50 daily median"},
                }
            )
        return rows

    def _fetch_drought(self, ws: Watershed) -> list[dict]:
        """Normalized U.S. Drought Monitor DSCI (0-1) for the metro county."""
        if not ws.county_fips:
            return []
        value = drought.fetch_drought_index(ws.county_fips)
        if value is None:
            return []
        return [
            {
                "metric": "drought_index",
                "value": value,
                "unit": "dsci_frac",
                "observed_at": timezone.now(),
                "raw": {"fips": ws.county_fips, "source": "USDM DSCI/500"},
            }
        ]

    def _fetch_demographics(self, ws: Watershed) -> list[dict]:
        """Metro county population (2020 Census) as a water-demand signal."""
        if not ws.county_fips:
            return []
        pop = demographics.population_for(ws.county_fips)
        if pop is None:
            return []
        return [
            {
                "metric": "population",
                "value": float(pop),
                "unit": "people",
                "observed_at": timezone.now(),
                "raw": {"fips": ws.county_fips, "source": "2020 U.S. Census"},
            }
        ]
