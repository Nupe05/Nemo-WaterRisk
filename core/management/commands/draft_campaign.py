"""Feed the machine real angles: draft approval-gated social content from the
report's headline findings (or a custom angle), in the on-brand voice.

Each finding carries its own real figures, so the ContentAgent has the numbers
it needs and never has to invent any. Every draft lands in the approval queue;
nothing posts until you approve, and `post_scheduled` drips it out.

    python manage.py draft_campaign            # draft from all report findings
    python manage.py draft_campaign --angle "Your custom angle with a real number."
"""
from django.core.management.base import BaseCommand

from agents.content_agent import ContentAgent

# Headline findings from "The State of Data-Center Water Risk 2026". Numbers are
# real (Nemo's 2026 index); the agent is instructed to use only these figures.
REPORT_FINDINGS = [
    "Nemo's 2026 index ranks Northern Virginia — the world's largest data-center "
    "market — 10th of 14 major U.S. markets, with a suitability score of 56.3/100. "
    "Not because of water (headroom 61/100) but because of power: the PJM "
    "interconnection queue is among the most backlogged in the country (power "
    "availability 42/100). Power is the #1 siting constraint; water is the #2.",

    "The three fastest-growing Sun Belt data-center markets have the least water "
    "headroom of any major U.S. market on Nemo's 2026 index (0-100 scale, higher = "
    "more supply room): Phoenix 30, Salt Lake City 32, Reno 33. For contrast, the "
    "top of the scale: Quincy WA 88, Chicago 85, Columbus 81. The build-out is "
    "accelerating toward the thinnest margins.",

    "The best-scoring U.S. data-center markets on Nemo's 2026 combined water + "
    "power + hazard index are not the household names: Quincy WA 76.7, Omaha 67.7, "
    "Hillsboro OR 66.2. They are water-rich, faster to energize, and comparatively "
    "uncongested — the likely shape of the next build-out wave.",

    "Most of a data center's water footprint is upstream, at the power plants "
    "supplying it — so water risk and power risk compound in the same markets "
    "rather than offsetting. That is why Nemo scores water and power together, not "
    "in isolation. Evaluating one without the other misses how the constraint binds.",
]


class Command(BaseCommand):
    help = "Draft approval-gated social content from the report findings (or a custom angle)."

    def add_arguments(self, parser):
        parser.add_argument("--angle", default="", help="Draft one custom angle instead of the report findings.")

    def handle(self, *args, **options):
        angles = [options["angle"]] if options["angle"].strip() else REPORT_FINDINGS
        agent = ContentAgent()
        drafted, skipped = 0, 0

        for i, angle in enumerate(angles, 1):
            self.stdout.write(f"[{i}/{len(angles)}] drafting: {angle[:70]}...")
            result = agent.run(news_item=angle)
            if result.get("content_item"):
                drafted += 1
                self.stdout.write(self.style.SUCCESS(
                    f"    queued content #{result['content_item']} "
                    f"(approvals {result['approval_ids']})"
                ))
            else:
                skipped += 1
                self.stderr.write(self.style.WARNING("    skipped (LLM unavailable — set ANTHROPIC_API_KEY)"))

        self.stdout.write(self.style.SUCCESS(
            f"draft_campaign done: {drafted} drafted, {skipped} skipped. "
            f"Review in /admin, approve, and post_scheduled will drip them out."
        ))
