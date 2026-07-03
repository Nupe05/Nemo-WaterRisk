"""Approving a SEND_REPORT item renders the report and emails it."""
import pytest
from django.contrib.gis.geos import Point

from agents.action_runner import ActionError, execute_item
from core.models import ApprovalItem, MonitoredSite, Watershed, WaterRiskScore


@pytest.fixture
def scored_site(db):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River", usgs_site_no="09498500")
    site = MonitoredSite.objects.create(
        reference="PHX-DC-001", name="Phoenix Data Center Alpha",
        location=Point(-112.0, 33.0), watershed=ws, is_public_index=True,
    )
    WaterRiskScore.objects.create(
        watershed=ws, score=61.5,
        components={"streamflow_deficit": 71.4, "drought_index": 59.4, "withdrawal_pressure": 10.0},
    )
    return site


@pytest.mark.django_db
def test_send_report_emails_the_report(mailoutbox, scored_site):
    item = ApprovalItem.objects.create(
        content_type="customer_report",
        action_type=ApprovalItem.ActionType.SEND_REPORT,
        state=ApprovalItem.State.APPROVED,
        payload={"to": "buyer@datacorp.com", "site": "PHX-DC-001"},
    )
    execute_item(item)

    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.to == ["buyer@datacorp.com"]
    assert "Phoenix Data Center Alpha" in msg.subject
    assert "61.5" in msg.body  # the rendered report HTML
    assert msg.content_subtype == "html"

    item.refresh_from_db()
    assert item.state == ApprovalItem.State.EXECUTED


@pytest.mark.django_db
def test_send_report_missing_site_fails():
    item = ApprovalItem.objects.create(
        content_type="customer_report",
        action_type=ApprovalItem.ActionType.SEND_REPORT,
        state=ApprovalItem.State.APPROVED,
        payload={"to": "buyer@datacorp.com"},  # no site
    )
    with pytest.raises(ActionError):
        execute_item(item)
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.FAILED
