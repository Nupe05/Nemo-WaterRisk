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
        precip = records.filter(metric="precip_mm").aggregate(v=Avg("value"))["v"]

        notes = []
        # Baselines are placeholders — replace with per-watershed percentiles.
        flow_baseline = 100.0
        precip_baseline = 40.0

        sf = streamflow_deficit(flow, flow_baseline) if flow is not None else 0.0
        if flow is None:
            notes.append("no streamflow data in window")

        if precip is not None:
            pd = max(0.0, min(1.0, 1.0 - (precip / precip_baseline)))
        else:
            pd = 0.0
            notes.append("no precip data in window")

        # Withdrawal pressure proxy: count of EPA stress rows, saturating.
        stress_count = records.filter(metric="epa_stress_proxy").count()
        wp = min(1.0, stress_count / 50.0)

        return ScoreInputs(
            streamflow_deficit=sf,
            precip_deficit=pd,
            withdrawal_pressure=wp,
            notes=notes,
        )
