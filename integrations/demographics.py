"""County population as a water-demand (withdrawal pressure) signal.

Local population is the primary driver of municipal water withdrawals that
compete with a data center for the same watershed, so it's a defensible proxy
for demand-side pressure. Values are 2020 U.S. Census county populations — a
slow-moving structural factor, so a curated reference is appropriate and needs
no flaky runtime API. Extend COUNTY_POPULATION when you add metros.

Source: U.S. Census Bureau, 2020 Decennial Census (QuickFacts by county).
"""
from __future__ import annotations

# County FIPS -> 2020 Census resident population.
COUNTY_POPULATION: dict[str, int] = {
    "04013": 4_420_568,  # Maricopa County, AZ (Phoenix)
    "48113": 2_613_539,  # Dallas County, TX
    "13121": 1_066_710,  # Fulton County, GA (Atlanta)
    "51107": 420_959,    # Loudoun County, VA (Ashburn / Northern Virginia)
    "41065": 26_670,     # Wasco County, OR (The Dalles)
}

# Population that maps to maximum (1.0) demand pressure. ~5M ≈ the largest
# U.S. metro counties, so the biggest data-center markets saturate near the top.
PRESSURE_SATURATION = 5_000_000.0


def population_for(county_fips: str) -> int | None:
    """2020 Census population for a county FIPS, or None if not in the table."""
    return COUNTY_POPULATION.get((county_fips or "").strip())


def demand_pressure(population: float | None) -> float:
    """Normalize a population to a 0-1 withdrawal-pressure value."""
    if not population or population <= 0:
        return 0.0
    return max(0.0, min(1.0, population / PRESSURE_SATURATION))
