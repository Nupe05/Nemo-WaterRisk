"""DataPipelineAgent — nightly ingest from USGS / NOAA / EPA into PostGIS.

Runs unattended (no approval needed — it only writes to our own DB, takes no
external action). Each source is isolated so one failing API doesn't abort the
whole refresh.
"""
from __future__ import annotations

from django.utils import timezone

from core.models import RawDataRecord, Watershed
from integrations import epa, noaa, usgs
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
            ingested += self._ingest_source("noaa", ws, errors)
            ingested += self._ingest_source("epa", ws, errors)

        self.log("pipeline_finished", ingested=ingested, errors=len(errors))
        return {"ingested": ingested, "errors": errors, "at": timezone.now().isoformat()}

    def _ingest_source(self, source: str, ws: Watershed, errors: list[str]) -> int:
        try:
            if source == "usgs":
                rows = usgs.fetch_streamflow(ws.huc_code)
                src = RawDataRecord.Source.USGS
            elif source == "noaa":
                # state FIPS + window would come from watershed metadata in prod
                rows = noaa.fetch_drought_index("04", start="2024-01-01", end="2024-01-31")
                src = RawDataRecord.Source.NOAA
            else:
                rows = epa.fetch_withdrawal_proxy("AZ")
                src = RawDataRecord.Source.EPA
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
