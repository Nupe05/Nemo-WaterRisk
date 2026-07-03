"""A lead for a specific metro should queue an approval-gated report send."""
import pytest
from django.contrib.gis.geos import Point

from core.models import ApprovalItem, Lead, MonitoredSite, Watershed


@pytest.fixture
def site(db):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River", usgs_site_no="09498500")
    return MonitoredSite.objects.create(
        reference="PHX-DC-001", name="Phoenix", location=Point(-112.0, 33.0),
        watershed=ws, is_public_index=True,
    )


@pytest.mark.django_db
def test_lead_with_site_queues_report(client, site):
    client.post("/subscribe/", {"email": "buyer@datacorp.com", "site_ref": "PHX-DC-001"})
    assert Lead.objects.filter(email="buyer@datacorp.com").exists()
    item = ApprovalItem.objects.get(action_type=ApprovalItem.ActionType.SEND_REPORT)
    assert item.state == ApprovalItem.State.PENDING
    assert item.payload["to"] == "buyer@datacorp.com"
    assert item.payload["site"] == "PHX-DC-001"
    assert "Phoenix" in item.summary


@pytest.mark.django_db
def test_lead_without_site_queues_no_report(client, site):
    client.post("/subscribe/", {"email": "general@datacorp.com"})
    assert Lead.objects.filter(email="general@datacorp.com").exists()
    assert not ApprovalItem.objects.filter(
        action_type=ApprovalItem.ActionType.SEND_REPORT
    ).exists()


@pytest.mark.django_db
def test_lead_unknown_site_queues_no_report(client, site):
    client.post("/subscribe/", {"email": "x@datacorp.com", "site_ref": "NOPE-1"})
    assert not ApprovalItem.objects.filter(
        action_type=ApprovalItem.ActionType.SEND_REPORT
    ).exists()
