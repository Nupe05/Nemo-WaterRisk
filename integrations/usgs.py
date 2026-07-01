"""USGS NWIS water-services client.

Public API, no key required. Returns normalized records ready for
RawDataRecord. Docs: https://waterservices.usgs.gov/
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

BASE = os.getenv("USGS_BASE_URL", "https://waterservices.usgs.gov/nwis")
# 00060 = discharge (cfs), 00065 = gage height (ft)
DEFAULT_PARAM = "00060"


def fetch_streamflow(huc_code: str, *, param: str = DEFAULT_PARAM, timeout: int = 30) -> list[dict]:
    """Fetch the latest instantaneous streamflow for sites in a HUC.

    Returns a list of dicts: {metric, value, unit, observed_at, raw}.
    Network failures raise requests.RequestException (caller decides policy).
    """
    url = f"{BASE}/iv/"
    params = {
        "format": "json",
        "huc": huc_code,
        "parameterCd": param,
        "siteStatus": "active",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    out: list[dict] = []
    for series in data.get("value", {}).get("timeSeries", []):
        var = series.get("variable", {})
        unit = var.get("unit", {}).get("unitCode", "")
        for block in series.get("values", []):
            for point in block.get("value", []):
                try:
                    value = float(point["value"])
                except (KeyError, ValueError, TypeError):
                    continue
                observed = point.get("dateTime")
                out.append(
                    {
                        "metric": "streamflow_cfs" if param == "00060" else f"usgs_{param}",
                        "value": value,
                        "unit": unit,
                        "observed_at": _parse_dt(observed),
                        "raw": {"huc": huc_code, "param": param},
                    }
                )
    return out


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)
