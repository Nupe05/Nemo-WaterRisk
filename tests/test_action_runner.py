"""Security tests for the action runner: the approval gate and the path jail.

These are django DB tests (run with pytest-django + a test database).
They lock down the two things that must never regress:
  1. Nothing runs unless it is state=APPROVED.
  2. File writes cannot escape NEMO_WORKSPACE_ROOT.
"""
import pytest

from agents import action_runner
from agents.action_runner import ActionError, _safe_target
from core.models import ApprovalItem


# --- Path jail (no DB needed) ----------------------------------------------
@pytest.mark.parametrize(
    "bad",
    ["/etc/passwd", "../secrets", "a/../../b", "..\\win", "", None],
)
def test_safe_target_rejects_escapes(bad, settings, tmp_path):
    settings.NEMO = {**settings.NEMO, "WORKSPACE_ROOT": str(tmp_path)}
    with pytest.raises(ActionError):
        _safe_target(bad)


def test_safe_target_accepts_relative(settings, tmp_path):
    settings.NEMO = {**settings.NEMO, "WORKSPACE_ROOT": str(tmp_path)}
    target = _safe_target("reports/out.pdf")
    assert str(target).startswith(str(tmp_path))


# --- Approval gate (DB) -----------------------------------------------------
@pytest.mark.django_db
def test_runner_refuses_pending_item():
    item = ApprovalItem.objects.create(
        content_type="social_content",
        action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.PENDING,
        payload={"thread": ["hi"]},
    )
    with pytest.raises(ActionError):
        action_runner.execute_item(item)


@pytest.mark.django_db
def test_runner_executes_approved_item():
    item = ApprovalItem.objects.create(
        content_type="social_content",
        action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.APPROVED,
        payload={"thread": ["hi"]},
    )
    action_runner.execute_item(item)
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.EXECUTED


@pytest.mark.django_db
def test_run_approved_queue_skips_pending():
    ApprovalItem.objects.create(
        content_type="x", action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.PENDING, payload={},
    )
    approved = ApprovalItem.objects.create(
        content_type="x", action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.APPROVED, payload={"thread": []},
    )
    results = action_runner.run_approved_queue()
    ids = [r["id"] for r in results]
    assert approved.pk in ids and len(ids) == 1
