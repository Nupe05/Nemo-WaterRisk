"""Pure parser tests for the USGS client (no network, no DB).

Fixtures mirror the real API response shapes (verified against site 09498500,
Salt River near Roosevelt, AZ).
"""
from integrations import usgs

# --- Statistics (RDB) fixture: tab-delimited, with comment + format rows -----
RDB = "\n".join(
    [
        "# US Geological Survey daily statistics",
        "# comment lines start with hash",
        "\t".join(
            ["agency_cd", "site_no", "parameter_cd", "ts_id", "loc_web_ds",
             "month_nu", "day_nu", "begin_yr", "end_yr", "count_nu", "p50_va"]
        ),
        "\t".join(["5s", "15s", "5s", "10n", "15s", "3n", "3n", "6n", "6n", "8n", "12s"]),
        "\t".join(["USGS", "09498500", "00060", "5665", "", "7", "1", "1914", "2025", "112", "157"]),
        "\t".join(["USGS", "09498500", "00060", "5665", "", "7", "2", "1914", "2025", "112", "159"]),
        # a row with a missing median should be skipped, not crash
        "\t".join(["USGS", "09498500", "00060", "5665", "", "7", "3", "1914", "2025", "0", ""]),
    ]
)


def test_parse_daily_median_rdb():
    medians = usgs.parse_daily_median_rdb(RDB)
    assert medians[(7, 1)] == 157.0
    assert medians[(7, 2)] == 159.0
    assert (7, 3) not in medians  # blank p50 skipped


def test_parse_daily_median_rdb_empty():
    assert usgs.parse_daily_median_rdb("") == {}


# --- Instantaneous Values (JSON) fixture ------------------------------------
IV_JSON = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {"siteCode": [{"value": "09498500"}]},
                "variable": {"unit": {"unitCode": "ft3/s"}},
                "values": [
                    {"value": [{"value": "39.4", "dateTime": "2026-07-01T14:30:00.000-07:00"}]}
                ],
            }
        ]
    }
}


def test_parse_iv_json():
    rows = usgs._parse_iv_json(IV_JSON)
    assert len(rows) == 1
    assert rows[0]["site_no"] == "09498500"
    assert rows[0]["value"] == 39.4
    assert rows[0]["metric"] == "streamflow_cfs"
    assert rows[0]["unit"] == "ft3/s"


def test_parse_iv_json_skips_no_data():
    payload = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {"siteCode": [{"value": "01234567"}]},
                    "variable": {"unit": {"unitCode": "ft3/s"}},
                    "values": [{"value": [{"value": "-999999.0", "dateTime": "2026-07-01T00:00:00Z"}]}],
                }
            ]
        }
    }
    assert usgs._parse_iv_json(payload) == []
