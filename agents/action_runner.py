"""Action runner — executes APPROVED ApprovalItems, nothing else.

Two guarantees the prior system lacked:

1. Approval is enforced at execution time. `execute_item` refuses anything
   whose state is not APPROVED, so a draft can never leak out even if another
   code path calls the runner.

2. Path safety is enforced at execution time, not just at draft time. Every
   file write is resolved against NEMO_WORKSPACE_ROOT and rejected if it
   escapes that jail. The previous code validated the path only when the LLM
   proposed it, then wrote to `path || target` without re-checking.

The action type registry here is the SAME one the agents propose against
(ApprovalItem.ActionType) — a single shared vocabulary.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from core.models import ApprovalItem

logger = logging.getLogger("nemo.runner")


class ActionError(RuntimeError):
    pass


def _workspace_root() -> Path:
    root = Path(settings.NEMO["WORKSPACE_ROOT"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_target(relpath: str) -> Path:
    """Resolve `relpath` inside the workspace jail or raise."""
    if not relpath or not isinstance(relpath, str):
        raise ActionError("path_required")
    if relpath.startswith("/") or ".." in relpath.split("/") or "\\" in relpath:
        raise ActionError(f"unsafe_path:{relpath}")
    root = _workspace_root()
    target = (root / relpath).resolve()
    # Containment check: the resolved path must stay under the jail.
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise ActionError(f"path_escapes_workspace:{relpath}")
    return target


# --- Individual action handlers --------------------------------------------
def _run_write_file(payload: dict) -> dict:
    target = _safe_target(payload.get("path", ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(payload.get("content", "")), encoding="utf-8")
    return {"ok": True, "path": str(target)}


def _run_send_report(payload: dict) -> dict:
    # Stub: wire to your transactional email provider (SES/Postmark/etc).
    # Kept side-effect-free until real credentials + provider are configured.
    logger.info("send_report (stub) to=%s report=%s", payload.get("to"), payload.get("report_path"))
    return {"ok": True, "stub": True, "detail": "email provider not configured"}


def _run_post_twitter(payload: dict) -> dict:
    # Stub: integrate tweepy here once X credentials are set in env.
    logger.info("post_twitter (stub) posts=%s", len(payload.get("thread", [])))
    return {"ok": True, "stub": True, "detail": "X credentials not configured"}


def _run_post_youtube(payload: dict) -> dict:
    logger.info("post_youtube (stub) title=%s", payload.get("title"))
    return {"ok": True, "stub": True, "detail": "YouTube credentials not configured"}


def _run_post_instagram(payload: dict) -> dict:
    logger.info("post_instagram (stub) caption_len=%s", len(payload.get("caption", "")))
    return {"ok": True, "stub": True, "detail": "Instagram credentials not configured"}


_HANDLERS = {
    ApprovalItem.ActionType.WRITE_FILE: _run_write_file,
    ApprovalItem.ActionType.SEND_REPORT: _run_send_report,
    ApprovalItem.ActionType.POST_TWITTER: _run_post_twitter,
    ApprovalItem.ActionType.POST_YOUTUBE: _run_post_youtube,
    ApprovalItem.ActionType.POST_INSTAGRAM: _run_post_instagram,
}


def execute_item(item: ApprovalItem) -> ApprovalItem:
    """Execute one approved item. Refuses anything not in state APPROVED."""
    if item.state != ApprovalItem.State.APPROVED:
        raise ActionError(f"not_approved:{item.state}")

    handler = _HANDLERS.get(item.action_type)
    if handler is None:
        item.state = ApprovalItem.State.FAILED
        item.result = {"error": f"unsupported_action_type:{item.action_type}"}
        item.save(update_fields=["state", "result"])
        raise ActionError(f"unsupported_action_type:{item.action_type}")

    try:
        result = handler(item.payload or {})
        item.state = ApprovalItem.State.EXECUTED
        item.result = result
        item.executed_at = timezone.now()
        item.save(update_fields=["state", "result", "executed_at"])
        logger.info("action_executed id=%s type=%s", item.pk, item.action_type)
    except Exception as exc:  # noqa: BLE001
        item.state = ApprovalItem.State.FAILED
        item.result = {"error": str(exc)}
        item.save(update_fields=["state", "result"])
        logger.error("action_failed id=%s type=%s err=%s", item.pk, item.action_type, exc)
        raise ActionError(str(exc)) from exc
    return item


def run_approved_queue(limit: int = 50) -> list[dict]:
    """Execute all currently-approved items. Called by the distribution sweep."""
    results = []
    approved = ApprovalItem.objects.filter(state=ApprovalItem.State.APPROVED).order_by("created_at")[:limit]
    for item in approved:
        try:
            execute_item(item)
            results.append({"id": item.pk, "ok": True})
        except ActionError as exc:
            results.append({"id": item.pk, "ok": False, "error": str(exc)})
    return results
