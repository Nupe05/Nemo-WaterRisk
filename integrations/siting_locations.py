"""Candidate-location registry for the data-center siting engine.

This is the universe of counties the siting engine scores, grouped into the
metro markets developers actually shortlist. Each county carries:

  * identity: FIPS, county name, state FIPS, metro market
  * market_status: 'established' (existing DC cluster) or 'emerging'
  * water_headroom: curated 0-100 water-availability score (higher = more
    supply headroom for a new large cooling load) — the differentiated leg
    nobody else scores well.

Water headroom is a slow-moving structural factor (basin yield, aquifer
status, allocation regime, drought climatology), so a curated reference keyed
to public data is appropriate here just as county population is in
demographics.py. It is grounded in:
  * USGS Water Use / streamflow context (https://waterdata.usgs.gov)
  * U.S. Drought Monitor climatology (https://droughtmonitor.unl.edu)
  * State water-allocation status (e.g. AZ Groundwater Management Areas,
    Great Salt Lake / Colorado River shortage declarations, Edwards Aquifer)

Upgrade path: replace the static water_headroom with a live per-basin computed
value from the existing scoring engine (streamflow deficit + DSCI + demand),
rolled from the county's watershed. The registry stays the source of truth for
which counties belong to which metro.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    fips: str
    county: str
    state_fips: str
    metro: str
    market_status: str
    water_headroom: float  # 0-100, higher = more water supply headroom


# Ordered registry. Counties are grouped by metro; metros span the arid West
# (low water headroom — the story) to the water-rich Midwest/Northwest (high).
LOCATIONS: list[Location] = [
    # --- Northern Virginia (Ashburn) — the incumbent, power-constrained ---
    Location("51107", "Loudoun County", "51", "Northern Virginia (Ashburn)", "established", 62),
    Location("51153", "Prince William County", "51", "Northern Virginia (Ashburn)", "established", 60),
    # --- Phoenix — booming but arid: water is the constraint ---
    Location("04013", "Maricopa County", "04", "Phoenix, AZ", "established", 28),
    Location("04021", "Pinal County", "04", "Phoenix, AZ", "emerging", 32),
    # --- Dallas–Fort Worth — big ERCOT market, moderate water ---
    Location("48113", "Dallas County", "48", "Dallas–Fort Worth, TX", "established", 55),
    Location("48439", "Tarrant County", "48", "Dallas–Fort Worth, TX", "established", 54),
    Location("48139", "Ellis County", "48", "Dallas–Fort Worth, TX", "emerging", 57),
    # --- Atlanta — historically water-litigated (tri-state water war) ---
    Location("13121", "Fulton County", "13", "Atlanta, GA", "established", 50),
    Location("13097", "Douglas County", "13", "Atlanta, GA", "emerging", 52),
    # --- Columbus, OH (New Albany) — emerging star: power + strong water ---
    Location("39049", "Franklin County", "39", "Columbus, OH", "established", 82),
    Location("39089", "Licking County", "39", "Columbus, OH", "emerging", 80),
    # --- Chicago — Great Lakes water abundance ---
    Location("17031", "Cook County", "17", "Chicago, IL", "established", 85),
    # --- Salt Lake City — Great Salt Lake / Colorado River stress ---
    Location("49035", "Salt Lake County", "49", "Salt Lake City, UT", "established", 30),
    Location("49049", "Utah County", "49", "Salt Lake City, UT", "emerging", 33),
    # --- Hillsboro, OR (Silicon Forest) — Columbia/Willamette water ---
    Location("41067", "Washington County", "41", "Hillsboro, OR", "established", 70),
    Location("41051", "Multnomah County", "41", "Hillsboro, OR", "established", 68),
    # --- Reno, NV (Tahoe-Reno Industrial Center) — arid, limited river ---
    Location("32031", "Washoe County", "32", "Reno, NV", "established", 32),
    Location("32029", "Storey County", "32", "Reno, NV", "emerging", 34),
    # --- Santa Clara / Bay Area — imported, drought-prone water ---
    Location("06085", "Santa Clara County", "06", "Santa Clara, CA", "established", 38),
    # --- Des Moines, IA — river-fed, ample supply ---
    Location("19153", "Polk County", "19", "Des Moines, IA", "emerging", 72),
    # --- San Antonio, TX — Edwards Aquifer limits, semi-arid ---
    Location("48029", "Bexar County", "48", "San Antonio, TX", "emerging", 42),
    # --- Omaha, NE — Missouri/Platte water, low cost ---
    Location("31055", "Douglas County", "31", "Omaha, NE", "emerging", 75),
    # --- Quincy, WA — Columbia River + hydro: why it became a DC hub ---
    Location("53025", "Grant County", "53", "Quincy, WA", "established", 88),
]


def metros() -> list[str]:
    """Distinct metro market names, preserving registry order."""
    seen: list[str] = []
    for loc in LOCATIONS:
        if loc.metro not in seen:
            seen.append(loc.metro)
    return seen
