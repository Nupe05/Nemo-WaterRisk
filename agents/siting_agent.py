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

from integrations import grid, hazard
from integrations.siting_locations import LOCATIONS
from scoring.siting import SitingInputs, WEIGHTS, compute_suitability

from .base import BaseAgent

# Neutral fallback when a leg has no data for a location, so one missing input
# doesn't silently zero out an otherwise-strong site.
NEUTRAL = 50.0


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


class SitingAgent(BaseAgent):
    name = "siting"

    def run(self) -> dict:
        from core.models import SitingLocation, SitingScore

        weights = _weights()
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

            water = float(loc.water_headroom)
            power_prof = grid.power_availability(loc.state_fips)
            hazard_prof = hazard.hazard_safety(loc.fips)
            power = power_prof["score"] if power_prof else NEUTRAL
            hz = hazard_prof["score"] if hazard_prof else NEUTRAL

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
                    "top_hazards": hazard_prof["top_hazards"] if hazard_prof else [],
                },
            )
            created.append(score)

        # National rank across this run (1 = best).
        created.sort(key=lambda s: s.suitability, reverse=True)
        for i, score in enumerate(created, start=1):
            score.rank = i
            score.save(update_fields=["rank"])

        best = created[0] if created else None
        self.log(
            "siting_scored",
            counties=len(created),
            best=best.location.county_name if best else None,
            best_score=best.suitability if best else None,
        )
        return {
            "counties_scored": len(created),
            "top": [
                {"county": s.location.county_name, "metro": s.location.metro,
                 "suitability": s.suitability, "grade": s.grade}
                for s in created[:5]
            ],
        }
