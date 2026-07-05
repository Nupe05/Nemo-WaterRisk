"""draft_campaign feeds report findings to the ContentAgent (LLM mocked)."""
import pytest
from django.core.management import call_command

from agents.base import BaseAgent
from core.management.commands.draft_campaign import REPORT_FINDINGS
from core.models import ApprovalItem, ContentItem

DRAFT = {
    "youtube_outline": "Northern Virginia ranks 10th of 14...",
    "twitter_thread": ["56.3/100 for the world's largest DC market"] + [f"post {i}" for i in range(2, 8)],
    "instagram_caption": "Power, not water, is the binding constraint.",
    "visual_brief": "Bar chart of the 14-market ranking.",
}


@pytest.mark.django_db
def test_campaign_drafts_content_for_every_finding(monkeypatch):
    monkeypatch.setattr(BaseAgent, "think_json", lambda self, *a, **k: DRAFT)

    call_command("draft_campaign")

    # One ContentItem per finding, three approvals (X/IG/YT) each.
    assert ContentItem.objects.count() == len(REPORT_FINDINGS)
    assert ApprovalItem.objects.filter(content_type="social_content").count() == 3 * len(REPORT_FINDINGS)
    assert ApprovalItem.objects.filter(
        action_type=ApprovalItem.ActionType.POST_TWITTER, state=ApprovalItem.State.PENDING
    ).count() == len(REPORT_FINDINGS)


@pytest.mark.django_db
def test_campaign_single_custom_angle(monkeypatch):
    monkeypatch.setattr(BaseAgent, "think_json", lambda self, *a, **k: DRAFT)

    call_command("draft_campaign", "--angle", "Phoenix water headroom is 30/100, the lowest on the index.")

    assert ContentItem.objects.count() == 1
    assert ApprovalItem.objects.filter(content_type="social_content").count() == 3


@pytest.mark.django_db
def test_campaign_skips_when_llm_unavailable(monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(BaseAgent, "think_json", boom)
    call_command("draft_campaign")

    # No junk queued when the LLM is down.
    assert ContentItem.objects.count() == 0
    assert ApprovalItem.objects.filter(content_type="social_content").count() == 0
