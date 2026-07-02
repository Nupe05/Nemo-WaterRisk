"""Autonomous daily refresh — the entrypoint for Heroku Scheduler.

Runs the full build pipeline (ingest latest USGS/NOAA/EPA data -> rescore ->
draft content for any material risk changes) and prints a one-line summary for
the scheduler logs. Safe to run unattended: it takes no external action itself
(any content it drafts goes to the approval queue, never posted automatically).

    python manage.py daily_refresh
"""
from django.core.management.base import BaseCommand

from orchestrator import runner


class Command(BaseCommand):
    help = "Autonomous daily refresh: ingest, rescore, and draft content for risk changes."

    def handle(self, *args, **options):
        result = runner.build_pipeline()
        pipeline = result.get("pipeline", {}) or {}
        scoring = result.get("scoring", {}) or {}
        summary = (
            "daily_refresh complete: "
            f"ingested={pipeline.get('ingested', 0)} "
            f"scored={scoring.get('scored', 0)} "
            f"changes={scoring.get('changes', 0)} "
            f"content_drafted={result.get('content_drafted', 0)}"
        )
        errors = pipeline.get("errors") or []
        if errors:
            summary += f" errors={len(errors)}"
        self.stdout.write(self.style.SUCCESS(summary))
