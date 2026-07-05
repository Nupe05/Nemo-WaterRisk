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
    "You write for Nemo Water Risk, the INDEPENDENT RATING AUTHORITY for "
    "data-center water risk. Audience: data-center developers, operators, and the "
    "people financing them. "
    "VOICE: authoritative and institutional — measured, numbers-forward, neutral. "
    "Sound like a rating agency, not a startup. Short, declarative sentences. No "
    "hype words ('revolutionary', 'game-changing'), no alarmism, no emojis. "
    "POSITIONING to reinforce: power is the #1 constraint on data-center siting, "
    "water is the emerging #2, and the two compound (most of a data center's water "
    "footprint is upstream at its power plants). Nemo fuses water, power, and "
    "natural-hazard data into one independent, decision-grade score. Tagline when a "
    "sign-off fits: 'Know the water before you build.' "
    "CRITICAL RULE: use ONLY numbers that appear in the trigger text. NEVER invent, "
    "estimate, or round to new figures. If the trigger has no number, write "
    "qualitatively rather than fabricate one. "
    "Return ONLY JSON with keys: youtube_outline (string, <=180 words), twitter_thread "
    "(array of exactly 7 short strings; the first must lead with a specific figure "
    "drawn from the trigger), instagram_caption (string, <=150 words), visual_brief "
    "(string, <=40 words describing a chart or map). Keep within these limits."
)


class ContentAgent(BaseAgent):
    name = "content"

    def run(self, *, risk_change_id: int | None = None, news_item: str = "") -> dict:
        change = RiskChange.objects.filter(pk=risk_change_id).select_related("watershed").first()
        trigger = self._describe_trigger(change, news_item)

        draft = self._draft(trigger)
        if not draft:
            # LLM unavailable/failed: skip rather than queue placeholder junk.
            self.log("content_skipped", risk_change_id=risk_change_id, reason="llm_unavailable")
            if change is not None:
                change.content_generated = True
                change.save(update_fields=["content_generated"])
            return {"content_item": None, "approval_ids": [], "skipped": True}

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

    def _draft(self, trigger: str) -> dict | None:
        try:
            # Generous budget so the multi-part JSON is never truncated mid-string.
            return self.think_json(_SYSTEM, f"Trigger event: {trigger}", temperature=0.4, max_tokens=4096)
        except Exception as exc:  # noqa: BLE001 - skip (caller queues nothing)
            self.log("content_llm_failed", error=str(exc))
            return None
