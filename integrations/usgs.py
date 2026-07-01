"""USGS NWIS client.

Two public, key-free services:

* Instantaneous Values (IV) — current streamflow per gauge site.
* Statistics (stat) — historical daily median flow, used as the baseline the
  current flow is compared against so the risk score reflects "low vs normal
  for this day of year" rather than an arbitrary constant.

Network I/O and parsing are separated so the parsers are unit-testable with
fixtures and no network. Docs: https://waterservices.usgs.gov/
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

BASE = os.getenv("USGS_BASE_URL", "https://waterservices.usgs.gov/nwis")
DISCHARGE = "00060"  # streamflow, cubic feet per second
_NO_DATA = -999999.0


# --------------------------------------------------------------------------
# Instantaneous Values (current flow)
# --------------------------------------------------------------------------
def fetch_latest_by_sites(site_ids, *, param: str = DISCHARGE, timeout: int = 30) -> list[dict]:
    """Latest instantaneous value for each USGS site number.

    Returns dicts: {site_no, metric, value, unit, observed_at, raw}.
    """
    sites = [s for s in (site_ids or []) if s]
    if not sites:
        return []
    resp = requests.get(
        f"{BASE}/iv/",
        params={
            "format": "json",
            "sites": ",".join(sites),
            "parameterCd": param,
            "siteStatus": "all",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return _parse_iv_json(resp.json(), param)


def _parse_iv_json(data: dict, param: str = DISCHARGE) -> list[dict]:
    out: list[dict] = []
    for series in (data or {}).get("value", {}).get("timeSeries", []):
        site_codes = series.get("sourceInfo", {}).get("siteCode", [])
        site_no = site_codes[0].get("value") if site_codes else None
        unit = series.get("variable", {}).get("unit", {}).get("unitCode", "")
        for block in series.get("values", []):
            for point in block.get("value", []):
                try:
                    value = float(point["value"])
                except (KeyError, ValueError, TypeError):
                    continue
                if value == _NO_DATA:
                    continue
                out.append(
                    {
                        "site_no": site_no,
                        "metric": "streamflow_cfs",
                        "value": value,
                        "unit": unit or "ft3/s",
                        "observed_at": _parse_dt(point.get("dateTime")),
                        "raw": {"site_no": site_no, "param": param},
                    }
                )
    return out


# --------------------------------------------------------------------------
# Statistics (historical daily median baseline)
# --------------------------------------------------------------------------
def fetch_daily_median(site_id: str, *, param: str = DISCHARGE, timeout: int = 30) -> dict:
    """Return {(month, day): median_cfs} of historical daily-mean flow."""
    resp = requests.get(
        f"{BASE}/stat/",
        params={
            "format": "rdb",
            "sites": site_id,
            "statReportType": "daily",
            "statTypeCd": "median",
            "parameterCd": param,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_daily_median_rdb(resp.text)


def parse_daily_median_rdb(text: str) -> dict:
    """Parse a USGS 'stat' RDB response into {(month, day): p50_cfs}.

    RDB format: comment lines start with '#', then a header row of column
    names, then a format row (e.g. '5s\\t15s\\t...'), then tab-delimited data.
    """
    result: dict[tuple[int, int], float] = {}
    header: list[str] | None = None
    for line in (text or "").splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            continue
        if cols and cols[0].strip().endswith("s") and cols[0][0].isdigit():
            continue  # RDB format/definition row like '5s'
        row = dict(zip(header, cols))
        try:
            month = int(row["month_nu"])
            day = int(row["day_nu"])
            p50 = float(row["p50_va"])
        except (KeyError, ValueError):
            continue
        result[(month, day)] = p50
    return result


def median_for_date(site_id: str, when: datetime | None = None, **kwargs) -> float | None:
    """Historical median flow for the given date's day-of-year (default: today)."""
    when = when or datetime.now(timezone.utc)
    medians = fetch_daily_median(site_id, **kwargs)
    return medians.get((when.month, when.day))


# --------------------------------------------------------------------------
# HUC-based fallback (broad, when no specific gauge is configured)
# --------------------------------------------------------------------------
def fetch_streamflow(huc_code: str, *, param: str = DISCHARGE, timeout: int = 30) -> list[dict]:
    """Latest streamflow for active sites within a HUC. Fallback path."""
    resp = requests.get(
        f"{BASE}/iv/",
        params={"format": "json", "huc": huc_code, "parameterCd": param, "siteStatus": "active"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return _parse_iv_json(resp.json(), param)


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)
