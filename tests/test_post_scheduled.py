"""Scheduled posting drips approved social items oldest-first (no network)."""
import pytest
from django.core.management import call_command

from core.models import ApprovalItem


def _item(action=ApprovalItem.ActionType.POST_INSTAGRAM):
    # Instagram execution is a stub (no external creds), ideal for testing the drip.
    return ApprovalItem.objects.create(
        content_type="social_content",
        action_type=action,
        state=ApprovalItem.State.APPROVED,
        payload={"caption": "x"},
    )


@pytest.mark.django_db
def test_drips_oldest_first_up_to_limit():
    a, b, c = _item(), _item(), _item()  # created oldest -> newest
    call_command("post_scheduled", "--limit", "2")

    for x in (a, b, c):
        x.refresh_from_db()
    # the two oldest posted, the newest still queued
    assert a.state == ApprovalItem.State.EXECUTED
    assert b.state == ApprovalItem.State.EXECUTED
    assert c.state == ApprovalItem.State.APPROVED


@pytest.mark.django_db
def test_ignores_non_social_and_unapproved():
    ApprovalItem.objects.create(
        content_type="customer_report", action_type=ApprovalItem.ActionType.SEND_REPORT,
        state=ApprovalItem.State.APPROVED, payload={"to": "x@y.com", "site": "PHX-DC-001"},
    )
    pending = _item()
    pending.state = ApprovalItem.State.PENDING
    pending.save()

    call_command("post_scheduled", "--limit", "5")

    # the report wasn't touched by post_scheduled, and pending stays pending
    pending.refresh_from_db()
    assert pending.state == ApprovalItem.State.PENDING
    assert not ApprovalItem.objects.filter(
        action_type=ApprovalItem.ActionType.SEND_REPORT, state=ApprovalItem.State.EXECUTED
    ).exists()
