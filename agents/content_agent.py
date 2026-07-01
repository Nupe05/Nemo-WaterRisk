"""ContentAgent — turn a risk signal into multi-platform draft content.

Triggered by a RiskChange (our own data) or an external news item. Drafts a
YouTube outline, an X thread, and an Instagram caption + visual brief in one
call, stores them as a ContentItem, and queues each platform post as its own
approval item. Nothing posts without your sign-off.
"""
from __future__ import annotations

from core.models import ApprovalItem, ContentItem, RiskChange
from .base import BaseAgent

_SYSTEM = (
    "You are a content strategist for a data-intelligence company that tracks "
    "water risk for data centers. Authoritative, data-driven, never sensational. "
    "Always cite specific numbers. Audience: data-center developers and ESG analysts. "
    "Return ONLY JSON with keys: youtube_outline (string), twitter_thread (array of "
    "7 strings; first item must be a stat), instagram_caption (string, <=150 words), "
    "visual_brief (string describing a chart or map to generate)."
)


class ContentAgent(BaseAgent):
    name = "content"

    def run(self, *, risk_change_id: int | None = None, news_item: str = "") -> dict:
        change = RiskChange.objects.filter(pk=risk_change_id).select_related("watershed").first()
        trigger = self._describe_trigger(change, news_item)

        draft = self._draft(trigger)
        item = ContentItem.objects.create(
            trigger_change=change,
            youtube_outline=draft.get("youtube_outline", ""),
            twitter_thread=draft.get("twitter_thread", []),
            instagram_caption=draft.get("instagram_caption", ""),
            visual_brief=draft.get("visual_brief", ""),
        )

        approvals = [
            self.queue_for_approval(
                content_type="social_content",
                action_type=ApprovalItem.ActionType.POST_TWITTER,
                payload={"thread": item.twitter_thread, "content_item": item.pk},
                summary="X thread: " + (item.twitter_thread[0][:80] if item.twitter_thread else ""),
            ),
            self.queue_for_approval(
                content_type="social_content",
                action_type=ApprovalItem.ActionType.POST_INSTAGRAM,
                payload={"caption": item.instagram_caption, "content_item": item.pk},
                summary="IG caption",
            ),
            self.queue_for_approval(
                content_type="social_content",
                action_type=ApprovalItem.ActionType.POST_YOUTUBE,
                payload={"outline": item.youtube_outline, "content_item": item.pk},
                summary="YouTube outline",
            ),
        ]

        if change is not None:
            change.content_generated = True
            change.save(update_fields=["content_generated"])

        return {"content_item": item.pk, "approval_ids": [a.pk for a in approvals]}

    def _describe_trigger(self, change: RiskChange | None, news_item: str) -> str:
        if change is not None:
            return (
                f"Watershed {change.watershed.name} risk moved from "
                f"{change.previous_score} to {change.new_score} "
                f"(Δ{change.magnitude})."
            )
        return news_item or "General water-risk industry update."

    def _draft(self, trigger: str) -> dict:
        try:
            return self.think_json(_SYSTEM, f"Trigger event: {trigger}", temperature=0.4)
        except Exception as exc:  # noqa: BLE001 - degrade to a minimal draft
            self.log("content_llm_failed", error=str(exc))
            return {
                "youtube_outline": f"[DRAFT NEEDED] {trigger}",
                "twitter_thread": [f"[DRAFT NEEDED] {trigger}"],
                "instagram_caption": f"[DRAFT NEEDED] {trigger}",
                "visual_brief": "Bar chart of risk score change over time.",
            }
