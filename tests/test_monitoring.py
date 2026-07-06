"""Monitoring & alerts: signup, direction-aware sweep, tiers, dedupe, delivery."""
import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone

from core.models import (
    AlertEvent,
    ApprovalItem,
    MonitorSubscription,
    MonitoredSite,
    SitingChange,
    SitingScore,
    Watershed,
    WaterRiskScore,
)


# --- fixtures ---------------------------------------------------------------
@pytest.fixture
def site(db):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River")
    s = MonitoredSite.objects.create(
        reference="PHX-DC-001",
        name="Phoenix Data Center Alpha",
        location=Point(-112.074, 33.448),
        watershed=ws,
        is_public_index=True,
    )
    WaterRiskScore.objects.create(watershed=ws, score=67.0, components={})  # High
    return s


def _add_score(site, value, when=None):
    WaterRiskScore.objects.create(
        watershed=site.watershed, score=value, components={},
        computed_at=when or timezone.now(),
    )


def _sweep():
    from agents.monitor_agent import MonitorAgent
    return MonitorAgent().run()


# --- signup -----------------------------------------------------------------
@pytest.mark.django_db
def test_signup_creates_site_subscription_and_lead(client, site):
    from core.models import Lead

    resp = client.post("/monitor/subscribe/", {
        "email": "ops@datacorp.com", "target_type": "site",
        "target_ref": "PHX-DC-001", "tier": "pro",
    })
    assert resp.status_code == 302
    sub = MonitorSubscription.objects.get()
    assert sub.email == "ops@datacorp.com" and sub.target_type == "site" and sub.tier == "pro"
    assert Lead.objects.filter(email="ops@datacorp.com", source="monitor_signup").exists()


@pytest.mark.django_db
def test_signup_is_idempotent_per_target(client, site):
    payload = {"email": "ops@datacorp.com", "target_type": "site", "target_ref": "PHX-DC-001"}
    client.post("/monitor/subscribe/", payload)
    client.post("/monitor/subscribe/", payload)  # same target again
    assert MonitorSubscription.objects.filter(email="ops@datacorp.com").count() == 1


# --- sweep behavior ---------------------------------------------------------
@pytest.mark.django_db
def test_first_sweep_baselines_without_alerting(site):
    MonitorSubscription.objects.create(email="a@b.com", target_type="site", target_ref="PHX-DC-001")
    result = _sweep()
    assert result["alerts_queued"] == 0
    sub = MonitorSubscription.objects.get()
    assert sub.last_alerted_score == 67.0  # baseline captured
    assert not ApprovalItem.objects.filter(action_type=ApprovalItem.ActionType.SEND_ALERT).exists()


@pytest.mark.django_db
def test_alert_fires_on_band_worsening_then_dedupes(site):
    MonitorSubscription.objects.create(email="a@b.com", target_type="site", target_ref="PHX-DC-001")
    _sweep()                       # baseline at 67 (High)
    _add_score(site, 85.0)         # -> Severe: worse band
    result = _sweep()
    assert result["alerts_queued"] == 1
    item = ApprovalItem.objects.get(action_type=ApprovalItem.ActionType.SEND_ALERT)
    assert item.state == ApprovalItem.State.PENDING
    assert item.payload["to"] == "a@b.com"
    assert item.payload["to_band"] == "Severe" and item.payload["from_band"] == "High"
    assert AlertEvent.objects.count() == 1

    # nothing new changed -> no duplicate alert
    assert _sweep()["alerts_queued"] == 0
    assert ApprovalItem.objects.filter(action_type=ApprovalItem.ActionType.SEND_ALERT).count() == 1


@pytest.mark.django_db
def test_pro_tier_more_sensitive_than_basic(site):
    basic = MonitorSubscription.objects.create(email="basic@b.com", target_type="site", target_ref="PHX-DC-001", tier="basic")
    pro = MonitorSubscription.objects.create(email="pro@b.com", target_type="site", target_ref="PHX-DC-001", tier="pro")
    _sweep()                       # baseline both at 67
    _add_score(site, 72.0)         # +5, still High band
    _sweep()
    assert AlertEvent.objects.filter(subscription=pro).count() == 1     # pro delta 3 -> alerts
    assert AlertEvent.objects.filter(subscription=basic).count() == 0   # basic delta 7 -> no


@pytest.mark.django_db
def test_improvement_does_not_alert(site):
    MonitorSubscription.objects.create(email="a@b.com", target_type="site", target_ref="PHX-DC-001")
    _sweep()                       # baseline 67
    _add_score(site, 40.0)         # improved (lower risk)
    assert _sweep()["alerts_queued"] == 0


# --- metro monitoring -------------------------------------------------------
@pytest.mark.django_db
def test_metro_alert_on_suitability_drop():
    from agents.siting_agent import SitingAgent
    SitingAgent().run()
    MonitorSubscription.objects.create(email="a@b.com", target_type="metro", target_ref="Phoenix, AZ")
    _sweep()  # baseline

    # Simulate a fresh, much worse run for Phoenix counties (higher=better, so drop).
    from core.models import SitingLocation
    for fips in ("04013", "04021"):
        loc = SitingLocation.objects.get(county_fips=fips)
        SitingScore.objects.create(location=loc, suitability=15.0, water=10, power=15, hazard=20,
                                   grade="Challenged", computed_at=timezone.now())
    result = _sweep()
    assert result["alerts_queued"] == 1
    item = ApprovalItem.objects.get(action_type=ApprovalItem.ActionType.SEND_ALERT)
    assert item.payload["target_type"] == "metro"
    assert item.payload["metric"] == "siting suitability"


# --- delivery ---------------------------------------------------------------
@pytest.mark.django_db
def test_send_alert_handler_emails_on_approval(mailoutbox):
    from agents.action_runner import execute_item

    item = ApprovalItem.objects.create(
        content_type="monitor_alert",
        action_type=ApprovalItem.ActionType.SEND_ALERT,
        state=ApprovalItem.State.APPROVED,
        payload={
            "to": "a@b.com", "target_label": "Phoenix Data Center Alpha",
            "metric": "water-supply risk", "direction": "increased",
            "from_score": 67, "to_score": 85, "from_band": "High", "to_band": "Severe",
            "detail_path": "/site/PHX-DC-001/", "tier": "pro",
        },
    )
    execute_item(item)
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["a@b.com"]
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.EXECUTED


# --- siting change emission -------------------------------------------------
@pytest.mark.django_db
def test_siting_agent_emits_change_on_material_move():
    from agents.siting_agent import SitingAgent
    from core.models import SitingLocation

    # Seed a prior score for Quincy's county far from what the agent will compute.
    loc = SitingLocation.objects.create(
        county_fips="53025", county_name="Grant County", state_fips="53",
        metro="Quincy, WA", market_status="established",
    )
    SitingScore.objects.create(location=loc, suitability=30.0, water=30, power=30, hazard=30,
                               grade="Challenged", computed_at=timezone.now())

    SitingAgent().run()  # recomputes Grant to ~76.7 -> big move
    assert SitingChange.objects.filter(metro="Quincy, WA").exists()
    change = SitingChange.objects.get(metro="Quincy, WA")
    assert change.magnitude >= 3.0
