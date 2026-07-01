"""NOAA drought / precipitation client.

Uses the NCEI CDO API (token via NOAA_TOKEN). If no token is configured the
functions return an empty list so the pipeline degrades gracefully rather
than crashing. Docs: https://www.ncdc.noaa.gov/cdo-web/webservices/v2
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

CDO_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2"


def fetch_drought_index(fips_state: str, *, start: str, end: str, timeout: int = 30) -> list[dict]:
    """Fetch a drought/precip proxy for a state FIPS over a date range.

    Returns [] when NOAA_TOKEN is unset (graceful degradation).
    """
    token = os.getenv("NOAA_TOKEN", "")
    if not token:
        return []

    resp = requests.get(
        f"{CDO_BASE}/data",
        headers={"token": token},
        params={
            "datasetid": "GHCND",
            "datatypeid": "PRCP",
            "locationid": f"FIPS:{fips_state}",
            "startdate": start,
            "enddate": end,
            "units": "metric",
            "limit": 1000,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()

    out: list[dict] = []
    for row in payload.get("results", []):
        try:
            value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(
            {
                "metric": "precip_mm",
                "value": value,
                "unit": "mm",
                "observed_at": _parse_dt(row.get("date")),
                "raw": {"station": row.get("station"), "fips": fips_state},
            }
        )
    return out


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
