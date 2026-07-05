"""Live-data hardening: drought overlay on water, NRI context, provenance, toggle."""
import pytest

from integrations import drought, hazard


def _grant_score():
    from core.models import SitingScore
    return SitingScore.objects.select_related("location").get(location__county_fips="53025")


@pytest.mark.django_db
def test_drought_discounts_water_headroom(monkeypatch):
    # Extreme drought everywhere; default penalty 0.5 halves structural headroom.
    monkeypatch.setattr(drought, "fetch_drought_index", lambda fips, **k: 1.0)
    monkeypatch.setattr(hazard, "fetch_nri_rating", lambda fips, **k: None)
    from agents.siting_agent import SitingAgent

    SitingAgent().run()
    grant = _grant_score()
    # Grant, WA structural water headroom is 88 -> ~44 at max drought.
    assert grant.water == pytest.approx(44.0, abs=0.5)
    assert "USDM" in grant.detail["water_source"]


@pytest.mark.django_db
def test_falls_back_to_structural_when_feed_down(monkeypatch):
    monkeypatch.setattr(drought, "fetch_drought_index", lambda fips, **k: None)
    monkeypatch.setattr(hazard, "fetch_nri_rating", lambda fips, **k: None)
    from agents.siting_agent import SitingAgent

    SitingAgent().run()
    grant = _grant_score()
    assert grant.water == 88.0                      # unchanged structural baseline
    assert grant.detail["water_source"] == "structural"


@pytest.mark.django_db
def test_nri_rating_attached_as_context(monkeypatch):
    monkeypatch.setattr(drought, "fetch_drought_index", lambda fips, **k: None)
    monkeypatch.setattr(
        hazard, "fetch_nri_rating",
        lambda fips, **k: {"risk_rating": "Very High", "risk_score": 99.9},
    )
    from agents.siting_agent import SitingAgent

    SitingAgent().run()
    grant = _grant_score()
    assert grant.detail["nri_risk_rating"] == "Very High"
    assert grant.detail["nri_risk_score"] == 99.9
    # ...but NRI does not drive the hazard leg — hazard stays the structural model.
    assert grant.detail["hazard_source"].startswith("structural")
    assert grant.hazard == 78.0                     # Grant structural hazard safety


@pytest.mark.django_db
def test_live_toggle_off_skips_external_calls(monkeypatch):
    monkeypatch.setenv("NEMO_SITING_LIVE", "0")

    def boom(*a, **k):
        raise AssertionError("live fetch called while disabled")

    monkeypatch.setattr(drought, "fetch_drought_index", boom)
    monkeypatch.setattr(hazard, "fetch_nri_rating", boom)
    from agents.siting_agent import SitingAgent

    SitingAgent().run()                              # must not raise
    grant = _grant_score()
    assert grant.water == 88.0
    assert grant.detail["water_source"] == "structural"
    assert grant.detail["nri_risk_rating"] is None


@pytest.mark.django_db
def test_power_carries_source_provenance(monkeypatch):
    monkeypatch.setattr(drought, "fetch_drought_index", lambda fips, **k: None)
    monkeypatch.setattr(hazard, "fetch_nri_rating", lambda fips, **k: None)
    from agents.siting_agent import SitingAgent

    SitingAgent().run()
    grant = _grant_score()
    assert "LBNL" in (grant.detail.get("power_source") or "")
