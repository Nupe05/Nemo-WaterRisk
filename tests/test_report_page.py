"""The public, citable State-of-Water-Risk report page + data endpoint."""
import json

import pytest


@pytest.fixture
def scored(db):
    from agents.siting_agent import SitingAgent
    SitingAgent().run()  # NEMO_SITING_LIVE defaults off in conftest -> offline


@pytest.mark.django_db
def test_report_page_renders_live(client, scored):
    resp = client.get("/report/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "The State of Data-Center Water Risk" in body
    assert "National ranking" in body
    assert "Quincy" in body                     # top market appears in the table
    assert "Northern Virginia" in body          # flagship finding


@pytest.mark.django_db
def test_report_data_endpoint(client, scored):
    resp = client.get("/report/data/")
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["publisher"] == "Nemo Water Risk"
    assert data["market_count"] == len(data["markets"]) > 0
    top = data["markets"][0]
    assert top["rank"] == 1
    assert {"market", "suitability", "grade", "water_headroom", "power_availability", "hazard_safety"} <= set(top)
    # ranking is best-first
    scores = [m["suitability"] for m in data["markets"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.django_db
def test_report_page_handles_no_data(client):
    resp = client.get("/report/")          # nothing scored yet
    assert resp.status_code == 200
    assert "has not been scored" in resp.content.decode()


@pytest.mark.django_db
def test_report_data_url_not_shadowed_by_site_report(client, scored):
    # /report/data/ must resolve to the JSON endpoint, not the site-report param route.
    resp = client.get("/report/data/")
    assert resp["Content-Type"].startswith("application/json")
