"""ScoringAgent — recompute water-risk scores and flag material changes.

Reads recent RawDataRecords, computes a WaterRiskScore per watershed, and
emits a RiskChange when the score moves by more than the configured threshold
(default 5 points). RiskChange rows are the trigger that wakes the ContentAgent
and the customer-alert path.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Avg
from django.utils import timezone

from core.models import RawDataRecord, RiskChange, Watershed, WaterRiskScore
from integrations.demographics import demand_pressure
from scoring.model import ScoreInputs, compute_score, streamflow_deficit
from .base import BaseAgent


class ScoringAgent(BaseAgent):
    name = "scoring"

    def run(self, *, lookback_days: int = 7) -> dict:
        threshold = settings.NEMO["RISK_CHANGE_THRESHOLD"]
        since = timezone.now() - timedelta(days=lookback_days)
        scored, changes = 0, 0

        for ws in Watershed.objects.all():
            inputs = self._build_inputs(ws, since)
            result = compute_score(inputs)

            previous = WaterRiskScore.objects.filter(watershed=ws).order_by("-computed_at").first()
            score_obj = WaterRiskScore.objects.create(
                watershed=ws, score=result["score"], components=result["components"]
            )
            scored += 1

            if previous is not None:
                magnitude = abs(result["score"] - previous.score)
                if magnitude >= threshold:
                    RiskChange.objects.create(
                        watershed=ws,
                        previous_score=previous.score,
                        new_score=result["score"],
                        magnitude=round(magnitude, 2),
                    )
                    changes += 1
                    self.log("risk_change_flagged", huc=ws.huc_code, magnitude=magnitude)

        self.log("scoring_finished", scored=scored, changes=changes)
        return {"scored": scored, "changes": changes}

    def _build_inputs(self, ws: Watershed, since) -> ScoreInputs:
        """Derive 0-1 stress indicators from recent records.

        This is intentionally simple and transparent. Baselines should come
        from historical percentiles per watershed once you have history.
        """
        records = RawDataRecord.objects.filter(watershed=ws, observed_at__gte=since)

        flow = records.filter(metric="streamflow_cfs").aggregate(v=Avg("value"))["v"]
        # Real baseline: USGS historical daily median for this day-of-year,
        # ingested by the pipeline. Falls back to a constant only if absent.
        median = records.filter(metric="streamflow_median_cfs").aggregate(v=Avg("value"))["v"]
        # Drought stress: normalized U.S. Drought Monitor DSCI (already 0-1).
        drought = records.filter(metric="drought_index").aggregate(v=Avg("value"))["v"]

        notes = []

        if median and median > 0:
            flow_baseline = median
        else:
            flow_baseline = 100.0
            notes.append("no USGS baseline available; using fallback flow baseline")

        sf = streamflow_deficit(flow, flow_baseline) if flow is not None else 0.0
        if flow is None:
            notes.append("no streamflow data in window")

        if drought is not None:
            di = max(0.0, min(1.0, drought))
        else:
            di = 0.0
            notes.append("no drought data in window")

        # Withdrawal pressure: metro population (2020 Census) as a water-demand
        # proxy, normalized to 0-1 by the demographics integration.
        population = records.filter(metric="population").aggregate(v=Avg("value"))["v"]
        wp = demand_pressure(population)
        if population is None:
            notes.append("no population data in window")

        return ScoreInputs(
            streamflow_deficit=sf,
            drought_index=di,
            withdrawal_pressure=wp,
            notes=notes,
        )
