"""Siting engine: composite math, integrations, agent, public surface, revenue loop."""
import pytest

from integrations import grid, hazard
from scoring.siting import SitingInputs, compute_suitability, grade_for


# --- Pure model (no DB) -----------------------------------------------------
def test_composite_is_weighted_and_higher_is_better():
    strong = compute_suitability(SitingInputs(water=90, power=90, hazard=90))
    weak = compute_suitability(SitingInputs(water=10, power=10, hazard=10))
    assert strong["score"] > weak["score"]
    assert strong["score"] == pytest.approx(90.0, abs=0.1)
    assert strong["grade"] == "Prime"
    assert weak["grade"] == "Challenged"


def test_power_dominates_by_weight():
    """Power is weighted heaviest, so a great grid outranks great water alone."""
    good_power = compute_suitability(SitingInputs(water=0, power=100, hazard=0))
    good_water = compute_suitability(SitingInputs(water=100, power=0, hazard=0))
    assert good_power["score"] > good_water["score"]


def test_weights_need_not_sum_to_one():
    r = compute_suitability(SitingInputs(water=50, power=50, hazard=50),
                            weights={"power": 2, "water": 2, "hazard": 2})
    assert r["score"] == pytest.approx(50.0, abs=0.1)


def test_grade_bands():
    assert grade_for(85)[0] == "Prime"
    assert grade_for(70)[0] == "Strong"
    assert grade_for(55)[0] == "Viable"
    assert grade_for(40)[0] == "Marginal"
    assert grade_for(10)[0] == "Challenged"
    assert grade_for(None)[0] == "Unknown"


# --- Integrations -----------------------------------------------------------
def test_power_availability_maps_texas_and_virginia():
    tx = grid.power_availability("48")   # ERCOT — fast
    va = grid.power_availability("51")   # PJM — backlogged
    assert tx["region"] == "ERCOT" and va["region"] == "PJM"
    assert tx["score"] > va["score"]     # Texas easier to energize than N. Virginia
    assert grid.power_availability("99") is None


def test_hazard_safety_shapes():
    h = hazard.hazard_safety("06085")    # Santa Clara — high seismic
    assert 0 <= h["score"] <= 100
    assert "earthquake" in h["top_hazards"]
    assert hazard.hazard_safety("00000") is None


# --- Agent + persistence (DB) ----------------------------------------------
@pytest.mark.django_db
def test_agent_scores_ranks_and_persists():
    from agents.siting_agent import SitingAgent
    from core.models import SitingLocation, SitingScore

    result = SitingAgent().run()
    assert result["counties_scored"] > 0
    assert SitingLocation.objects.count() == result["counties_scored"]
    # ranks are dense 1..N and unique
    ranks = sorted(SitingScore.objects.values_list("rank", flat=True))
    assert ranks == list(range(1, len(ranks) + 1))
    # a water-rich, low-hazard market (Quincy/Columbus/Chicago) should beat Phoenix
    best = SitingScore.objects.order_by("rank").first()
    phx = SitingScore.objects.filter(location__metro__startswith="Phoenix").first()
    assert best.suitability > phx.suitability


@pytest.mark.django_db
def test_agent_is_idempotent_on_locations():
    from agents.siting_agent import SitingAgent
    from core.models import SitingLocation

    SitingAgent().run()
    n = SitingLocation.objects.count()
    SitingAgent().run()               # second run must not duplicate locations
    assert SitingLocation.objects.count() == n


# --- Public surface + revenue loop -----------------------------------------
@pytest.mark.django_db
def test_siting_index_renders_best_first(client):
    from agents.siting_agent import SitingAgent
    SitingAgent().run()
    resp = client.get("/siting/")
    assert resp.status_code == 200
    assert b"Siting Index" in resp.content


@pytest.mark.django_db
def test_subscribe_captures_lead_and_queues_report(client):
    from agents.siting_agent import SitingAgent
    from core.models import ApprovalItem, Lead
    SitingAgent().run()

    resp = client.post("/siting/subscribe/", {"email": "buyer@datacorp.com", "metro": "Phoenix, AZ"})
    assert resp.status_code == 302
    assert Lead.objects.filter(email="buyer@datacorp.com", source="siting_index").exists()
    item = ApprovalItem.objects.get(action_type=ApprovalItem.ActionType.SEND_SITING_REPORT)
    assert item.state == ApprovalItem.State.PENDING
    assert item.payload["metro"] == "Phoenix, AZ"


@pytest.mark.django_db
def test_siting_report_send_runs_on_approval(mailoutbox):
    from agents.action_runner import execute_item
    from agents.siting_agent import SitingAgent
    from core.models import ApprovalItem
    SitingAgent().run()

    item = ApprovalItem.objects.create(
        content_type="siting_report",
        action_type=ApprovalItem.ActionType.SEND_SITING_REPORT,
        state=ApprovalItem.State.APPROVED,
        payload={"to": "buyer@datacorp.com", "metro": "Phoenix, AZ"},
    )
    execute_item(item)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["buyer@datacorp.com"]
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.EXECUTED


@pytest.mark.django_db
def test_report_context_none_for_unknown_metro():
    from core.siting_views import siting_report_context
    assert siting_report_context("Atlantis, ZZ") is None
