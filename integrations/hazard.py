"""Physical-hazard safety as a data-center siting signal.

Natural-hazard exposure matters twice for a data center: it drives facility
and business-interruption insurance cost, and extreme heat directly raises
cooling load (and therefore water and power draw). We fold the major hazards
into a single 0-100 SAFETY score per county, where a HIGHER score means LOWER
hazard exposure (more favorable for siting) — so it composes in the same
"higher = better" direction as the power and water legs.

Values are derived from FEMA's National Risk Index (NRI), the authoritative
county-level composite of 18 natural hazards (riverine/coastal flooding,
wildfire, earthquake, heat wave, tornado, hurricane, etc.). We invert the NRI
risk rating into a safety score and record the one or two hazards that drive a
county's exposure.

Source: FEMA National Risk Index, county level
  https://hazards.fema.gov/nri/  (data + API available)

Upgrade path: pull the FEMA NRI county CSV/API directly and compute
safety = 100 - normalized(RISK_SCORE); optionally weight the heat-wave and
riverine-flood components higher for data-center relevance.
"""
from __future__ import annotations

# County FIPS -> physical-hazard profile.
#   safety:       0-100 (higher = lower hazard exposure = more favorable)
#   top_hazards:  primary hazards driving the exposure, for the report
HAZARDS: dict[str, dict] = {
    # --- Northern Virginia (Ashburn) — low, stable inland exposure ---
    "51107": {"safety": 74, "top_hazards": ["riverine flooding"]},           # Loudoun, VA
    "51153": {"safety": 71, "top_hazards": ["riverine flooding", "wind"]},   # Prince William, VA
    # --- Phoenix — heat + drought elevate NRI ---
    "04013": {"safety": 55, "top_hazards": ["heat wave", "riverine flooding"]},  # Maricopa, AZ
    "04021": {"safety": 60, "top_hazards": ["heat wave"]},                    # Pinal, AZ
    # --- Dallas–Fort Worth — tornado/hail/heat belt ---
    "48113": {"safety": 52, "top_hazards": ["tornado", "hail", "heat wave"]}, # Dallas, TX
    "48439": {"safety": 50, "top_hazards": ["tornado", "hail"]},             # Tarrant, TX
    "48139": {"safety": 58, "top_hazards": ["tornado", "hail"]},             # Ellis, TX
    # --- Atlanta — moderate inland exposure ---
    "13121": {"safety": 60, "top_hazards": ["wind", "riverine flooding"]},   # Fulton, GA
    "13097": {"safety": 63, "top_hazards": ["wind"]},                        # Douglas, GA
    # --- Columbus, OH — low hazard ---
    "39049": {"safety": 74, "top_hazards": ["riverine flooding"]},           # Franklin, OH
    "39089": {"safety": 76, "top_hazards": ["riverine flooding"]},           # Licking, OH
    # --- Chicago — moderate (flood, winter storm) ---
    "17031": {"safety": 58, "top_hazards": ["riverine flooding", "winter weather"]},  # Cook, IL
    # --- Salt Lake — Wasatch seismic ---
    "49035": {"safety": 56, "top_hazards": ["earthquake"]},                  # Salt Lake, UT
    "49049": {"safety": 58, "top_hazards": ["earthquake"]},                  # Utah County, UT
    # --- Hillsboro, OR — Cascadia seismic, low frequency ---
    "41067": {"safety": 64, "top_hazards": ["earthquake"]},                  # Washington, OR
    "41051": {"safety": 61, "top_hazards": ["earthquake", "riverine flooding"]},  # Multnomah, OR
    # --- Reno — seismic + wildfire ---
    "32031": {"safety": 55, "top_hazards": ["earthquake", "wildfire"]},      # Washoe, NV
    "32029": {"safety": 58, "top_hazards": ["earthquake"]},                  # Storey, NV
    # --- Santa Clara — high seismic ---
    "06085": {"safety": 40, "top_hazards": ["earthquake"]},                  # Santa Clara, CA
    # --- Des Moines — low, some flood/tornado ---
    "19153": {"safety": 66, "top_hazards": ["tornado", "riverine flooding"]},# Polk, IA
    # --- San Antonio — flash flood + heat ---
    "48029": {"safety": 56, "top_hazards": ["riverine flooding", "heat wave"]},  # Bexar, TX
    # --- Omaha — tornado + river flood ---
    "31055": {"safety": 60, "top_hazards": ["tornado", "riverine flooding"]},# Douglas, NE
    # --- Quincy, WA — very low hazard, abundant hydro ---
    "53025": {"safety": 78, "top_hazards": ["wildfire"]},                    # Grant, WA
}


def hazard_safety(county_fips: str) -> dict | None:
    """Physical-hazard safety profile for a county FIPS.

    Returns {'score': 0-100, 'top_hazards': [...]} where a HIGHER score means
    LOWER natural-hazard exposure, or None if the county is not in the table.
    """
    prof = HAZARDS.get((county_fips or "").strip())
    if not prof:
        return None
    return {"score": float(prof["safety"]), "top_hazards": list(prof["top_hazards"])}
