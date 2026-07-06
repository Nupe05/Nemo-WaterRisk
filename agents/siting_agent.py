"""SitingAgent — scores candidate counties for data-center suitability.

Deterministic and LLM-free (a credibility core, like the water-risk scorer).
It seeds the SitingLocation registry, pulls the three favorability legs
(water headroom, power availability, hazard safety) from the integrations,
composes them into a 0-100 suitability score + grade, persists a SitingScore
per county, and assigns a national rank (1 = best this run).

Nothing here touches the outside world, so it needs no approval gate — it only
reads public/curated data and writes scores. The revenue action (emailing a
report) is separate and stays approval-gated.
"""
from __future__ import annotations

import os

from integrations import drought, grid, hazard
from integrations.siting_locations import LOCATIONS
from scoring.siting import SitingInputs, WEIGHTS, compute_suitability

from .base import BaseAgent

# Neutral fallback when a leg has no data for a location, so one missing input
# doesn't silently zero out an otherwise-strong site.
NEUTRAL = 50.0


def _live_enabled() -> bool:
    """Live external data (USDM drought, FEMA NRI) on unless NEMO_SITING_LIVE is
    explicitly disabled. Fetches always fall back to the structural snapshot."""
    return (os.getenv("NEMO_SITING_LIVE", "1").strip().lower() not in {"0", "false", "no"})


def _drought_penalty() -> float:
    """Max fraction of water headroom removed under extreme (DSCI-max) drought.
    Env NEMO_WATER_DROUGHT_PENALTY, default 0.5."""
    try:
        return max(0.0, min(1.0, float(os.getenv("NEMO_WATER_DROUGHT_PENALTY", "0.5"))))
    except ValueError:
        return 0.5


def _weights() -> dict:
    """Weights from env NEMO_SITING_WEIGHTS ('power:0.4,water:0.35,hazard:0.25')
    or the model default. Normalized by the scorer, so they need not sum to 1."""
    raw = (os.getenv("NEMO_SITING_WEIGHTS") or "").strip()
    if not raw:
        return WEIGHTS
    out: dict[str, float] = {}
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                continue
    return out or WEIGHTS


def _change_threshold() -> float:
    """Metro-suitability move (points) that counts as material. Env override:
    NEMO_SITING_CHANGE_THRESHOLD (default 3.0)."""
    try:
        return float(os.getenv("NEMO_SITING_CHANGE_THRESHOLD", "3.0"))
    except ValueError:
        return 3.0


class SitingAgent(BaseAgent):
    name = "siting"

    def run(self) -> dict:
        from core.models import SitingChange, SitingLocation, SitingScore

        weights = _weights()
        live = _live_enabled()
        # Snapshot prior metro composites BEFORE we write the new run, so we can
        # emit a SitingChange for any metro whose suitability moved materially.
        prior_metro = self._metro_composites()
        created = []

        for loc in LOCATIONS:
            location, _ = SitingLocation.objects.get_or_create(
                county_fips=loc.fips,
                defaults={
                    "county_name": loc.county,
                    "state_fips": loc.state_fips,
                    "metro": loc.metro,
                    "market_status": loc.market_status,
                },
            )

            water, water_source = self._water_leg(loc.water_headroom, loc.fips, live)
            power_prof = grid.power_availability(loc.state_fips)
            hazard_prof = hazard.hazard_safety(loc.fips)
            power = power_prof["score"] if power_prof else NEUTRAL
            hz = hazard_prof["score"] if hazard_prof else NEUTRAL

            # Live FEMA National Risk Index — authoritative rating, shown as
            # context; NOT fed into the hazard leg (see integrations/hazard.py).
            nri = hazard.fetch_nri_rating(loc.fips) if live else None

            result = compute_suitability(
                SitingInputs(water=water, power=power, hazard=hz), weights
            )

            score = SitingScore.objects.create(
                location=location,
                suitability=result["score"],
                water=round(water, 1),
                power=round(power, 1),
                hazard=round(hz, 1),
                grade=result["grade"],
                detail={
                    "weights": result["weights"],
                    "market_status": loc.market_status,
                    "power_region": power_prof["region"] if power_prof else None,
                    "power_years": power_prof["years"] if power_prof else None,
                    "power_note": power_prof["note"] if power_prof else None,
                    "power_source": power_prof["source"] if power_prof else None,
                    "top_hazards": hazard_prof["top_hazards"] if hazard_prof else [],
                    "water_source": water_source,
                    "hazard_source": "structural (physical-hazard model)",
                    "nri_risk_rating": nri["risk_rating"] if nri else None,
                    "nri_risk_score": round(nri["risk_score"], 1) if nri and nri.get("risk_score") is not None else None,
                },
            )
            created.append(score)

        # National rank across this run (1 = best).
        created.sort(key=lambda s: s.suitability, reverse=True)
        for i, score in enumerate(created, start=1):
            score.rank = i
            score.save(update_fields=["rank"])

        # Emit SitingChange for metros that moved materially since the prior run.
        threshold = _change_threshold()
        new_metro = self._metro_composites(scores=created)
        changes = 0
        for metro, new_val in new_metro.items():
            prev_val = prior_metro.get(metro)
            if prev_val is None:
                continue
            magnitude = abs(new_val - prev_val)
            if magnitude >= threshold:
                SitingChange.objects.create(
                    metro=metro,
                    previous_score=prev_val,
                    new_score=new_val,
                    magnitude=round(magnitude, 2),
                )
                changes += 1

        best = created[0] if created else None
        self.log(
            "siting_scored",
            counties=len(created),
            best=best.location.county_name if best else None,
            best_score=best.suitability if best else None,
            metro_changes=changes,
        )
        return {
            "counties_scored": len(created),
            "metro_changes": changes,
            "top": [
                {"county": s.location.county_name, "metro": s.location.metro,
                 "suitability": s.suitability, "grade": s.grade}
                for s in created[:5]
            ],
        }

    @staticmethod
    def _water_leg(structural: float, fips: str, live: bool) -> tuple[float, str]:
        """Water headroom = structural baseline, discounted by CURRENT drought.

        Pulls the live U.S. Drought Monitor DSCI (0-1) for the county and removes
        up to NEMO_WATER_DROUGHT_PENALTY of headroom at maximum drought. Falls
        back to the structural baseline if the feed is unavailable. Returns
        (score, provenance-label).
        """
        structural = float(structural)
        if not live:
            return structural, "structural"
        try:
            stress = drought.fetch_drought_index(fips)  # 0-1 or None
        except Exception:  # noqa: BLE001 - overlay is best-effort
            stress = None
        if stress is None:
            return structural, "structural"
        stress = max(0.0, min(1.0, stress))
        adjusted = structural * (1.0 - _drought_penalty() * stress)
        return round(adjusted, 1), "structural + USDM drought (live)"

    @staticmethod
    def _metro_composites(scores=None) -> dict:
        """Mean suitability per metro. From `scores` if given, else from the
        latest persisted SitingScore per location (the previous run)."""
        from core.models import SitingScore

        if scores is None:
            seen = {}
            for s in SitingScore.objects.select_related("location").order_by("-computed_at"):
                if s.location_id not in seen:
                    seen[s.location_id] = s
            scores = list(seen.values())

        buckets: dict[str, list[float]] = {}
        for s in scores:
            buckets.setdefault(s.location.metro, []).append(s.suitability)
        return {m: round(sum(v) / len(v), 2) for m, v in buckets.items() if v}
