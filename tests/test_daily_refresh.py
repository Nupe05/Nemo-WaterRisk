"""daily_refresh should run the build pipeline and summarize it (no network)."""
from django.core.management import call_command

from orchestrator import runner


def test_daily_refresh_summarizes(monkeypatch, capsys):
    monkeypatch.setattr(
        runner,
        "build_pipeline",
        lambda: {
            "pipeline": {"ingested": 10, "errors": []},
            "scoring": {"scored": 5, "changes": 1},
            "content_drafted": 1,
        },
    )
    call_command("daily_refresh")
    out = capsys.readouterr().out
    assert "ingested=10" in out
    assert "scored=5" in out
    assert "changes=1" in out
    assert "content_drafted=1" in out
