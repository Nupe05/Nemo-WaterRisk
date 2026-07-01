"""BaseAgent — shared behaviour for every agent in the system.

Every agent:
* reasons via Claude (`think` / `think_json`),
* reads and writes through the Django ORM (transactional; no JSON-file races),
* and routes anything externally-visible through `queue_for_approval`.

An agent NEVER performs an external side effect directly. It proposes an
ApprovalItem; the action runner executes it only after a human approves.
"""
from __future__ import annotations

import logging

from core.models import ApprovalItem
from .llm_client import call_llm_json

logger = logging.getLogger("nemo.agents")


class BaseAgent:
    name = "base"

    def log(self, event: str, **fields):
        logger.info("%s %s", event, fields)

    def think_json(self, system_prompt: str, user_prompt: str, *, temperature: float = 0.2) -> dict:
        """Structured reasoning: returns a parsed JSON object from Claude."""
        return call_llm_json(system_prompt, user_prompt, temperature=temperature)

    def queue_for_approval(
        self,
        *,
        content_type: str,
        action_type: str,
        payload: dict,
        summary: str = "",
        task=None,
    ) -> ApprovalItem:
        """Create a PENDING approval row. This is the only path to the outside world.

        `action_type` must be a value in ApprovalItem.ActionType — the same
        registry the runner validates against.
        """
        valid = set(ApprovalItem.ActionType.values)
        if action_type not in valid:
            raise ValueError(f"unknown_action_type:{action_type}")

        item = ApprovalItem.objects.create(
            task=task,
            content_type=content_type,
            action_type=action_type,
            payload=payload,
            summary=summary[:512],
            state=ApprovalItem.State.PENDING,
        )
        self.log("queued_for_approval", approval_id=item.pk, action_type=action_type)
        return item

    def run(self, *args, **kwargs):  # pragma: no cover - interface
        raise NotImplementedError
