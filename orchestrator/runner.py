"""Orchestrator — runs the agent stages in the right order.

Design mirrors the strong pattern from the previous system's orchestrator, but
each stage is a small, testable function and all external actions remain behind
the approval queue.

Stages
------
build_pipeline:      DataPipelineAgent -> ScoringAgent -> ContentAgent/VisualAgent
                     for each freshly-flagged RiskChange. (Drafts only; no posting.)
distribution_sweep:  DistributionAgent executes APPROVED items.
"""
from __future__ import annotations

import logging

from core.models import RiskChange
from agents.content_agent import ContentAgent
from agents.distribution_agent import DistributionAgent
from agents.pipeline_agent import DataPipelineAgent
from agents.scoring_agent import ScoringAgent
from agents.visual_agent import VisualAgent

logger = logging.getLogger("nemo.orchestrator")


def build_pipeline() -> dict:
    """Nightly: refresh data, rescore, and draft content for new risk changes."""
    pipeline_result = DataPipelineAgent().run()
    scoring_result = ScoringAgent().run()

    drafted = 0
    for change in RiskChange.objects.filter(content_generated=False):
        content_result = ContentAgent().run(risk_change_id=change.pk)
        content_item = content_result.get("content_item")
        if content_item:  # skip visual/count when the LLM draft was skipped
            VisualAgent().run(content_item_id=content_item)
            drafted += 1

    summary = {
        "pipeline": pipeline_result,
        "scoring": scoring_result,
        "content_drafted": drafted,
    }
    logger.info("build_pipeline_complete %s", summary)
    return summary


def distribution_sweep(limit: int = 50) -> dict:
    """Morning: push everything you approved in the admin queue."""
    result = DistributionAgent().run(limit=limit)
    logger.info("distribution_sweep_complete %s", result)
    return result
