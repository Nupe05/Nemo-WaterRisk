"""Pure parser test for the U.S. Drought Monitor client (no network)."""
from integrations import drought

# Real-shaped USDM CSV (cumulative category percentages), newest row first.
CSV = "\n".join(
    [
        "MapDate,FIPS,County,State,None,D0,D1,D2,D3,D4,ValidStart,ValidEnd,StatisticFormatID",
        "20260630,04013,Maricopa County,AZ,0.00,100.00,100.00,97.22,0.00,0.00,2026-06-30,2026-07-06,1",
        "20260623,04013,Maricopa County,AZ,0.00,100.00,90.00,50.00,0.00,0.00,2026-06-23,2026-06-29,1",
    ]
)


def test_parse_dsci_picks_latest_and_normalizes():
    # DSCI = 100+100+97.22 = 297.22; /500 = 0.59444
    value = drought.parse_dsci_csv(CSV)
    assert round(value, 4) == 0.5944


def test_parse_dsci_empty():
    assert drought.parse_dsci_csv("") is None
    assert drought.parse_dsci_csv("MapDate,FIPS\n") is None


def test_parse_dsci_clamped():
    # A degenerate all-100 row would be 500/500 = 1.0
    csv = (
        "MapDate,FIPS,County,State,None,D0,D1,D2,D3,D4\n"
        "20260630,04013,X,AZ,0,100,100,100,100,100"
    )
    assert drought.parse_dsci_csv(csv) == 1.0
