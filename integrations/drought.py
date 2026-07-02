"""U.S. Drought Monitor client (tokenless, authoritative).

Returns a normalized drought-stress value in [0, 1] for a county FIPS, derived
from the published Drought Severity and Coverage Index (DSCI). DSCI is the sum
of the five cumulative drought-category area percentages (D0..D4), ranging
0-500; we divide by 500 to normalize. This is a defensible, standard drought
measure and needs no API key.

Docs: https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

BASE = (
    "https://usdmdataservices.unl.edu/api/CountyStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
)


def fetch_drought_index(fips: str, *, timeout: int = 30) -> float | None:
    """Latest normalized drought stress (0-1) for a county FIPS, or None."""
    end = date.today()
    start = end - timedelta(days=35)
    resp = requests.get(
        BASE,
        params={
            "aoi": fips,
            "startdate": f"{start.month}/{start.day}/{start.year}",
            "enddate": f"{end.month}/{end.day}/{end.year}",
            "statisticsType": 1,  # cumulative category percentages
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_dsci_csv(resp.text)


def parse_dsci_csv(text: str) -> float | None:
    """Parse USDM CSV -> normalized DSCI (0-1) for the most recent week."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    header = [h.strip() for h in lines[0].split(",")]
    try:
        idx = {name: header.index(name) for name in ("MapDate", "D0", "D1", "D2", "D3", "D4")}
    except ValueError:
        return None

    best_date, best_value = "", None
    for line in lines[1:]:
        cols = line.split(",")
        try:
            map_date = cols[idx["MapDate"]].strip()
            dsci = sum(float(cols[idx[c]]) for c in ("D0", "D1", "D2", "D3", "D4"))
        except (IndexError, ValueError):
            continue
        if map_date > best_date:  # YYYYMMDD strings sort chronologically
            best_date, best_value = map_date, min(1.0, max(0.0, dsci / 500.0))
    return best_value
