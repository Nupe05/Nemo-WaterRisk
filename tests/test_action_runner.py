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
def test_runner_executes_approved_item(settings, tmp_path):
    # write_file needs no external config, so it exercises the runner cleanly.
    settings.NEMO = {**settings.NEMO, "WORKSPACE_ROOT": str(tmp_path)}
    item = ApprovalItem.objects.create(
        content_type="report",
        action_type=ApprovalItem.ActionType.WRITE_FILE,
        state=ApprovalItem.State.APPROVED,
        payload={"path": "out.txt", "content": "hi"},
    )
    action_runner.execute_item(item)
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.EXECUTED
    assert (tmp_path / "out.txt").read_text() == "hi"


@pytest.mark.django_db
def test_run_approved_queue_skips_pending(settings, tmp_path):
    settings.NEMO = {**settings.NEMO, "WORKSPACE_ROOT": str(tmp_path)}
    ApprovalItem.objects.create(
        content_type="x", action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.PENDING, payload={},
    )
    approved = ApprovalItem.objects.create(
        content_type="report", action_type=ApprovalItem.ActionType.WRITE_FILE,
        state=ApprovalItem.State.APPROVED, payload={"path": "a.txt", "content": "y"},
    )
    results = action_runner.run_approved_queue()
    ids = [r["id"] for r in results]
    assert approved.pk in ids and len(ids) == 1
