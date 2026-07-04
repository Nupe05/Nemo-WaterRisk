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
    """Render the site's report and email it to the requester.

    Uses Django's email backend: the console backend (default) prints the email
    to the logs, so this works with no setup; configure SMTP to send for real.
    """
    from django.conf import settings
    from django.core.mail import EmailMessage
    from django.template.loader import render_to_string

    from core.models import MonitoredSite
    from core.views import _report_context

    to = (payload or {}).get("to")
    site_ref = (payload or {}).get("site")
    if not to or not site_ref:
        raise ActionError("send_report_missing_to_or_site")

    site = MonitoredSite.objects.filter(reference=site_ref).first()
    if site is None:
        raise ActionError(f"site_not_found:{site_ref}")

    # Email-safe template (tables + inline styles) so it renders in Gmail/Outlook.
    html = render_to_string("public/report_email.html", _report_context(site))
    message = EmailMessage(
        subject=f"Water Risk Report — {site.name}",
        body=html,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to],
    )
    message.content_subtype = "html"
    message.send(fail_silently=False)
    logger.info("send_report sent to=%s site=%s backend=%s", to, site_ref, settings.EMAIL_BACKEND)
    return {"ok": True, "to": to, "site": site_ref}


def _run_post_twitter(payload: dict) -> dict:
    """Publish an approved thread to X/Twitter via OAuth 1.0a user context.

    Reads the four keys from env (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN,
    X_ACCESS_SECRET). Each post is chained as a reply to the previous one to
    form a thread. Raises ActionError if credentials are missing or the API
    call fails, so a failed post is visible rather than silent.
    """
    thread = [str(p).strip() for p in (payload.get("thread") or []) if str(p).strip()]
    if not thread:
        raise ActionError("empty_thread")

    creds = {k: (os.getenv(k) or "").strip() for k in
             ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise ActionError(f"x_credentials_not_configured:{','.join(missing)}")

    try:
        import tweepy
    except ImportError as exc:  # pragma: no cover
        raise ActionError("tweepy_not_installed") from exc

    client = tweepy.Client(
        consumer_key=creds["X_API_KEY"],
        consumer_secret=creds["X_API_SECRET"],
        access_token=creds["X_ACCESS_TOKEN"],
        access_token_secret=creds["X_ACCESS_SECRET"],
    )

    tweet_ids, prev_id = [], None
    try:
        for post in thread:
            resp = client.create_tweet(text=post[:280], in_reply_to_tweet_id=prev_id)
            prev_id = resp.data["id"]
            tweet_ids.append(prev_id)
    except Exception as exc:  # noqa: BLE001 - normalize tweepy/API errors
        raise ActionError(f"x_post_failed:{exc} (posted {len(tweet_ids)}/{len(thread)})") from exc

    logger.info("post_twitter published %s posts, root=%s", len(tweet_ids), tweet_ids[0])
    return {
        "ok": True,
        "tweet_ids": tweet_ids,
        "url": f"https://x.com/NemoWaterRisk/status/{tweet_ids[0]}",
    }


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
