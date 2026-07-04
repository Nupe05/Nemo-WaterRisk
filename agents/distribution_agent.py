"""DistributionAgent — the ONLY agent that touches external post APIs.

It never reads drafts directly. It executes the approved queue via the shared
action_runner, which re-checks that each item is APPROVED before doing
anything. Platform posting itself lives in action_runner handlers (currently
stubs until X/YouTube/Instagram credentials are configured).
"""
from __future__ import annotations

from .action_runner import run_approved_queue
from .base import BaseAgent


class DistributionAgent(BaseAgent):
    name = "distribution"

    def run(self, *, limit: int = 50) -> dict:
        # Social posting is drip-scheduled by `post_scheduled`, so the sweep
        # skips it and handles everything else (email replies, reports).
        from core.models import ApprovalItem

        social = [
            ApprovalItem.ActionType.POST_TWITTER,
            ApprovalItem.ActionType.POST_INSTAGRAM,
            ApprovalItem.ActionType.POST_YOUTUBE,
        ]
        results = run_approved_queue(limit=limit, exclude=social)
        executed = sum(1 for r in results if r.get("ok"))
        self.log("distribution_sweep", executed=executed, total=len(results))
        return {"executed": executed, "results": results}
