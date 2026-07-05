"""Grid / power availability as a data-center siting signal.

Power is the #1 binding constraint on new data-center builds today: the
interconnection queue backlog and time-to-energize, not land or even water,
is what actually kills or delays projects. So the siting engine treats power
as its heaviest-weighted leg.

We score by the grid operator (ISO/RTO) a county sits in, because
interconnection timelines, queue backlog, and available headroom are
determined at the ISO/utility level, not the county level. Each region gets a
0-100 POWER AVAILABILITY score (higher = more favorable / faster to energize),
derived from published interconnection-queue volume, typical time-to-connect,
and load-growth headroom.

This is a curated, defensible v1 snapshot — a slow-moving structural factor,
not something that needs a flaky runtime API. Sources:
  * Lawrence Berkeley National Lab, "Queued Up 2024" interconnection dataset
    (https://emp.lbl.gov/queues)
  * ISO/RTO interconnection-queue and capacity reports (PJM, ERCOT, MISO, SPP)
  * EIA Form 860 / grid capacity data (https://www.eia.gov/electricity/data.php)

Upgrade path: replace REGIONS values with a periodic pull of the LBNL queue
dataset keyed by ISO, and blend in utility-level available-capacity where a
data-center developer already has a utility relationship.
"""
from __future__ import annotations

# ISO/RTO region -> power-availability profile.
#   score:   0-100 favorability for energizing a large new load (higher = better)
#   years:   typical time-to-interconnect for a large load, in years
#   note:    one-line rationale surfaced in reports
REGIONS: dict[str, dict] = {
    "ERCOT": {
        "score": 78, "years": "2-3",
        "note": "Connect-and-manage model and heavy new-build keep Texas the fastest large-load interconnect.",
    },
    "SPP": {
        "score": 66, "years": "3-4",
        "note": "Wind-rich Plains grid with moderate queue depth and real headroom outside congestion pockets.",
    },
    "NORTHWEST": {
        "score": 66, "years": "3-4",
        "note": "Low-cost hydro (BPA/PacifiCorp) but transmission-constrained in the busiest corridors.",
    },
    "SOUTHEAST": {
        "score": 62, "years": "3-4",
        "note": "Vertically integrated utilities (e.g. Georgia Power) can move fast for very large loads, but load growth is steep.",
    },
    "WECC_SW": {
        "score": 60, "years": "3-5",
        "note": "Arizona/Nevada utilities are building hard, but summer-peaking constraints slow new large loads.",
    },
    "MISO": {
        "score": 58, "years": "4-5",
        "note": "Large queue and long study cycles, though Midwest headroom exists away from load centers.",
    },
    "CAISO": {
        "score": 48, "years": "4-5",
        "note": "High energy costs and a congested, constrained grid make California a hard energize.",
    },
    "PJM": {
        "score": 42, "years": "4-7",
        "note": "The hottest data-center market is also the most backlogged: queue reform, capacity-price spikes, multi-year waits.",
    },
}

# State FIPS (2-digit) -> ISO/RTO region the state's data-center markets sit in.
# For states split across ISOs we map to the region containing the relevant
# data-center metros (documented per state).
STATE_TO_REGION: dict[str, str] = {
    "48": "ERCOT",       # Texas (Dallas, San Antonio, Austin) - ERCOT
    "51": "PJM",         # Virginia (Ashburn / Northern Virginia) - PJM
    "39": "PJM",         # Ohio (Columbus / New Albany) - PJM
    "17": "PJM",         # Illinois (Chicago) - PJM (ComEd)
    "13": "SOUTHEAST",   # Georgia (Atlanta) - Southern Co (non-ISO)
    "04": "WECC_SW",     # Arizona (Phoenix) - APS/SRP (WECC)
    "32": "WECC_SW",     # Nevada (Reno / Las Vegas) - NV Energy (WECC)
    "49": "WECC_SW",     # Utah (Salt Lake) - PacifiCorp (WECC)
    "41": "NORTHWEST",   # Oregon (Hillsboro) - PacifiCorp/BPA
    "53": "NORTHWEST",   # Washington (Quincy) - BPA hydro
    "06": "CAISO",       # California (Santa Clara / Bay Area) - CAISO
    "19": "MISO",        # Iowa (Des Moines) - MISO
    "31": "SPP",         # Nebraska (Omaha) - SPP
}


def region_for_state(state_fips: str) -> str | None:
    """ISO/RTO region key for a 2-digit state FIPS, or None if unmapped."""
    return STATE_TO_REGION.get((state_fips or "").strip()[:2])


def power_availability(state_fips: str) -> dict | None:
    """Power-availability profile for a county's state.

    Returns {'score': 0-100, 'years': str, 'region': str, 'note': str} where a
    HIGHER score is more favorable for siting (easier/faster to energize), or
    None if the state's region is not mapped.
    """
    region = region_for_state(state_fips)
    if not region:
        return None
    prof = REGIONS[region]
    return {
        "score": float(prof["score"]),
        "years": prof["years"],
        "region": region,
        "note": prof["note"],
        # Provenance: interconnection queues have no live API — this is a
        # periodically-refreshed snapshot of the authoritative annual dataset.
        "source": "LBNL 'Queued Up' (annual) + ISO/RTO queue reports",
    }
