"""Anthropic LLM client.

Ports the robust bits from the previous Node llm-client:
* model + limits read from env (no hardcoded model strings),
* hard timeout,
* response size ceiling,
* tolerant JSON extraction (handles code fences / surrounding prose),
and adds correct handling of Anthropic content blocks (the prior code's
`response.content[0].text` would crash on tool-use or empty blocks).
"""
import json
import re

from django.conf import settings


class LLMError(RuntimeError):
    pass


def _extract_text(message) -> str:
    """Concatenate all text blocks from an Anthropic message safely."""
    parts = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    text = "".join(parts).strip()
    if not text:
        raise LLMError("llm_empty_response")
    return text


def parse_json_object(text: str) -> dict:
    """Best-effort parse of a JSON object from model output."""
    if not text or not text.strip():
        raise LLMError("llm_empty_response")
    trimmed = text.strip()

    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", trimmed, re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    first, last = trimmed.find("{"), trimmed.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(trimmed[first : last + 1])
        except json.JSONDecodeError:
            pass

    raise LLMError("llm_invalid_json")


def call_llm_json(system_prompt: str, user_prompt: str, *, temperature: float = 0.2) -> dict:
    """Call Claude and return a parsed JSON object. Raises LLMError on failure."""
    cfg = settings.NEMO
    model = cfg.get("LLM_MODEL")
    if not model:
        raise LLMError("llm_missing_model")  # must be set in env

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMError("anthropic_sdk_not_installed") from exc

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    timeout_s = cfg["LLM_TIMEOUT_MS"] / 1000.0

    try:
        message = client.messages.create(
            model=model,
            max_tokens=cfg["LLM_MAX_TOKENS"],
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            timeout=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 - normalize SDK errors
        raise LLMError(f"llm_call_failed:{exc}") from exc

    text = _extract_text(message)
    if len(text) > cfg["LLM_MAX_RESPONSE_CHARS"]:
        raise LLMError(f"llm_response_too_large:{len(text)}")
    return parse_json_object(text)
