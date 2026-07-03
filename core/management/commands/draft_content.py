"""Draft marketing content for one site right now, and print it.

Runs the ContentAgent against a site's current score (using the configured
LLM), prints the AI-written X thread / Instagram caption / YouTube outline to
the console, and queues each as an approval item for review. Handy for testing
the LLM and for spinning up content on demand.

    python manage.py draft_content --site PHX-DC-001
"""
from django.core.management.base import BaseCommand

from agents.content_agent import ContentAgent
from core.models import ContentItem, MonitoredSite, WaterRiskScore
from scoring.bands import band


class Command(BaseCommand):
    help = "Run the ContentAgent for one site now and print the AI-drafted content."

    def add_arguments(self, parser):
        parser.add_argument("--site", required=True, help="MonitoredSite reference, e.g. PHX-DC-001")

    def handle(self, *args, **options):
        ref = options["site"]
        try:
            site = MonitoredSite.objects.select_related("watershed").get(reference=ref)
        except MonitoredSite.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"No site with reference {ref!r}."))
            return

        latest = (
            WaterRiskScore.objects.filter(watershed=site.watershed).order_by("-computed_at").first()
            if site.watershed_id
            else None
        )
        if latest is None:
            self.stderr.write(self.style.ERROR("No score yet — run 'run_orchestrator --stage build' first."))
            return

        label, _ = band(round(latest.score, 1))
        news = (
            f"{site.name} in the {site.watershed.name} watershed currently carries a water-supply "
            f"risk score of {latest.score:.0f}/100 ({label} risk). Component breakdown: {latest.components}."
        )

        self.stdout.write(f"Drafting content for {site.name} (score {latest.score:.0f}, {label}) ...\n")
        result = ContentAgent().run(news_item=news)
        if not result.get("content_item"):
            self.stderr.write(self.style.ERROR("LLM unavailable — no content drafted (nothing queued)."))
            return
        item = ContentItem.objects.get(pk=result["content_item"])

        self.stdout.write(self.style.SUCCESS("=== X / Twitter thread ==="))
        for i, post in enumerate(item.twitter_thread or [], 1):
            self.stdout.write(f"{i}. {post}")

        self.stdout.write(self.style.SUCCESS("\n=== Instagram caption ==="))
        self.stdout.write(item.instagram_caption or "(none)")

        self.stdout.write(self.style.SUCCESS("\n=== YouTube outline ==="))
        self.stdout.write(item.youtube_outline or "(none)")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nQueued {len(result['approval_ids'])} approval item(s) for review in /admin: "
                f"{result['approval_ids']}"
            )
        )
