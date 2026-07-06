"""MonitorAgent — turns risk changes into approval-gated customer alerts.

This is the recurring-revenue engine: for every active MonitorSubscription it
compares the target's current risk to the state we last alerted on, and when
the risk has moved *adversely* past the subscriber's tier threshold (or crossed
into a worse band), it drafts an alert email into the approval queue. Nothing
sends without a human approve click, same as every other outbound action.

Direction is handled per target so "worse" always means worse:
  * water-risk site  — score is 0-100 where HIGHER = worse (more risk)
  * siting metro     — score is 0-100 where HIGHER = better, so a DROP is worse

Deduplication is via the subscription's last_alerted_* fields: we only alert
when the current adverse state differs from what we already notified.
"""
from __future__ import annotations

import os

from django.utils.text import slugify

from scoring.bands import band as water_band

from .base import BaseAgent

# Tier sensitivity: minimum adverse point-move (within the same band) to alert.
# A band crossing always alerts regardless of tier.
TIER_DELTA = {"pro": 3.0, "basic": 7.0}


def _delta_for(tier: str) -> float:
    try:
        override = os.getenv(f"NEMO_ALERT_DELTA_{tier.upper()}")
        if override:
            return float(override)
    except ValueError:
        pass
    return TIER_DELTA.get(tier, TIER_DELTA["basic"])


class MonitorAgent(BaseAgent):
    name = "monitor"

    def run(self, *, limit: int = 500) -> dict:
        from core.models import AlertEvent, MonitorSubscription

        queued = 0
        checked = 0
        for sub in MonitorSubscription.objects.filter(active=True):
            state = self._current_state(sub)
            if state is None:
                continue
            checked += 1
            cur_score, cur_band = state["score"], state["band"]

            # First observation: set the baseline, don't alert on pre-existing risk.
            if sub.last_alerted_score is None:
                self._rebaseline(sub, cur_score, cur_band)
                continue

            worse = (
                cur_score - sub.last_alerted_score
                if state["higher_is_worse"]
                else sub.last_alerted_score - cur_score
            )
            band_changed = cur_band != sub.last_alerted_band
            delta = _delta_for(sub.tier)

            if (band_changed and worse > 0) or worse >= delta:
                approval = self._queue_alert(sub, state)
                AlertEvent.objects.create(
                    subscription=sub,
                    target_type=sub.target_type,
                    target_ref=sub.target_ref,
                    from_score=sub.last_alerted_score,
                    to_score=cur_score,
                    from_band=sub.last_alerted_band,
                    to_band=cur_band,
                    approval=approval,
                )
                self._rebaseline(sub, cur_score, cur_band)
                queued += 1
                if queued >= limit:
                    break
            elif worse <= -delta:
                # Material improvement: silently rebaseline so a later dip is
                # measured from the improved level (no alert on good news).
                self._rebaseline(sub, cur_score, cur_band)

        self.log("monitor_sweep", checked=checked, alerts_queued=queued)
        return {"checked": checked, "alerts_queued": queued}

    # --- helpers ------------------------------------------------------------
    def _current_state(self, sub) -> dict | None:
        from core.models import MonitorSubscription

        if sub.target_type == MonitorSubscription.TargetType.SITE:
            return self._site_state(sub.target_ref)
        return self._metro_state(sub.target_ref)

    @staticmethod
    def _site_state(reference: str) -> dict | None:
        from core.models import MonitoredSite, WaterRiskScore

        site = (
            MonitoredSite.objects.filter(reference=reference)
            .select_related("watershed")
            .first()
        )
        if not site or not site.watershed_id:
            return None
        latest = (
            WaterRiskScore.objects.filter(watershed=site.watershed)
            .order_by("-computed_at")
            .first()
        )
        if not latest:
            return None
        score = round(latest.score, 1)
        label, _ = water_band(score)
        return {
            "label_name": site.name,
            "score": score,
            "band": label,
            "metric": "water-supply risk",
            "direction_word": "increased",
            "detail_path": f"/site/{site.reference}/",
            "higher_is_worse": True,
        }

    @staticmethod
    def _metro_state(metro_name: str) -> dict | None:
        from core.siting_views import current_metro_score

        cur = current_metro_score(metro_name)
        if not cur:
            return None
        return {
            "label_name": cur["metro"],
            "score": round(cur["score"], 1),
            "band": cur["band"],
            "metric": "siting suitability",
            "direction_word": "declined",
            "detail_path": f"/siting/{slugify(cur['metro'])}/",
            "higher_is_worse": False,
        }

    @staticmethod
    def _rebaseline(sub, score, band_label) -> None:
        sub.last_alerted_score = score
        sub.last_alerted_band = band_label
        sub.save(update_fields=["last_alerted_score", "last_alerted_band"])

    def _queue_alert(self, sub, state):
        from core.models import ApprovalItem

        payload = {
            "to": sub.email,
            "target_type": sub.target_type,
            "target_label": state["label_name"],
            "metric": state["metric"],
            "direction": state["direction_word"],
            "from_score": sub.last_alerted_score,
            "to_score": state["score"],
            "from_band": sub.last_alerted_band,
            "to_band": state["band"],
            "detail_path": state["detail_path"],
            "tier": sub.tier,
        }
        summary = (
            f"Alert {state['label_name']} {sub.last_alerted_band}->{state['band']} "
            f"({sub.last_alerted_score}->{state['score']}) to {sub.email}"
        )
        return self.queue_for_approval(
            content_type="monitor_alert",
            action_type=ApprovalItem.ActionType.SEND_ALERT,
            payload=payload,
            summary=summary,
        )
