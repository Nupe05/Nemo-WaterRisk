"""Parser robustness for real model output (no network)."""
import pytest

from agents.llm_client import LLMError, parse_json_object


def test_parses_literal_newlines_in_strings():
    # Models often emit multi-line strings with raw newlines (invalid strict JSON).
    raw = '{"youtube_outline": "Hook\nSection one\nCall to action", "twitter_thread": ["a", "b"]}'
    out = parse_json_object(raw)
    assert "Section one" in out["youtube_outline"]
    assert out["twitter_thread"] == ["a", "b"]


def test_parses_prose_wrapped_json():
    raw = 'Sure, here is the JSON:\n{"k": "v"}\nHope that helps!'
    assert parse_json_object(raw)["k"] == "v"


def test_parses_code_fenced_json():
    raw = '```json\n{"k": "v"}\n```'
    assert parse_json_object(raw)["k"] == "v"


def test_empty_raises():
    with pytest.raises(LLMError):
        parse_json_object("")
