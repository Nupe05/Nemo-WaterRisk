"""EPA data client (water withdrawal / stress proxies).

Thin wrapper around EPA's Envirofacts REST service. Kept minimal and
defensive; returns [] on any structural surprise so the nightly pipeline
never hard-fails on a single source.
Docs: https://www.epa.gov/enviro/envirofacts-data-service-api
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

BASE = os.getenv("EPA_BASE_URL", "https://data.epa.gov/efservice")


def fetch_withdrawal_proxy(state_code: str, *, timeout: int = 30) -> list[dict]:
    """Return a coarse withdrawal/stress proxy per state.

    This is intentionally a placeholder query shape — swap the table/column
    for the specific EPA dataset you standardize on. Returns [] on failure.
    """
    url = f"{BASE}/T_DESIGN_FOR_ENVIRONMENT/STATE_CODE/{state_code}/JSON"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        rows = resp.json()
    except (requests.RequestException, ValueError):
        return []

    if not isinstance(rows, list):
        return []

    out: list[dict] = []
    for row in rows[:500]:
        out.append(
            {
                "metric": "epa_stress_proxy",
                "value": 1.0,  # replace with the real numeric column
                "unit": "count",
                "observed_at": datetime.now(timezone.utc),
                "raw": {"state": state_code, "source_row_keys": list(row.keys())[:5]},
            }
        )
    return out
