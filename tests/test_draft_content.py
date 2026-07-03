"""draft_content runs the ContentAgent and prints/queues drafts (LLM mocked)."""
import pytest
from django.contrib.gis.geos import Point
from django.core.management import call_command

from agents.base import BaseAgent
from core.models import ApprovalItem, ContentItem, MonitoredSite, Watershed, WaterRiskScore

DRAFT = {
    "youtube_outline": "Hook: Phoenix water risk is climbing...",
    "twitter_thread": ["61/100 High water risk in Phoenix", "post 2", "post 3"],
    "instagram_caption": "Phoenix faces elevated water-supply risk this summer.",
    "visual_brief": "Bar chart of the risk score components.",
}


@pytest.mark.django_db
def test_draft_content(monkeypatch, capsys):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River", usgs_site_no="09498500")
    MonitoredSite.objects.create(
        reference="PHX-DC-001", name="Phoenix", location=Point(-112.0, 33.0),
        watershed=ws, is_public_index=True,
    )
    WaterRiskScore.objects.create(watershed=ws, score=61.5, components={"streamflow_deficit": 74.9})

    # Mock the LLM so the test is deterministic and offline.
    monkeypatch.setattr(BaseAgent, "think_json", lambda self, *a, **k: DRAFT)

    call_command("draft_content", "--site", "PHX-DC-001")
    out = capsys.readouterr().out
    assert "61/100 High water risk in Phoenix" in out
    assert "Phoenix faces elevated" in out

    assert ContentItem.objects.count() == 1
    assert ApprovalItem.objects.filter(content_type="social_content").count() == 3


@pytest.mark.django_db
def test_draft_content_skips_when_llm_fails(monkeypatch, capsys):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River", usgs_site_no="09498500")
    MonitoredSite.objects.create(
        reference="PHX-DC-001", name="Phoenix", location=Point(-112.0, 33.0),
        watershed=ws, is_public_index=True,
    )
    WaterRiskScore.objects.create(watershed=ws, score=61.5, components={"streamflow_deficit": 74.9})

    def boom(self, *a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(BaseAgent, "think_json", boom)
    call_command("draft_content", "--site", "PHX-DC-001")

    # No placeholder content or approvals queued when the LLM fails.
    assert ContentItem.objects.count() == 0
    assert ApprovalItem.objects.filter(content_type="social_content").count() == 0
