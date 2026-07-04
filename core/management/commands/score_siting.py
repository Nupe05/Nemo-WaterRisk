"""Score every candidate county for data-center siting suitability, now.

Runs the SitingAgent: seeds the location registry, computes the water/power/
hazard composite for each county, persists a SitingScore, ranks them, and
prints the national top 10. Wire this to Heroku Scheduler (e.g. weekly) to keep
the public siting index fresh.

    python manage.py score_siting
"""
from django.core.management.base import BaseCommand

from agents.siting_agent import SitingAgent


class Command(BaseCommand):
    help = "Compute data-center siting suitability scores for all candidate counties."

    def handle(self, *args, **options):
        from core.models import SitingScore

        self.stdout.write("Scoring candidate counties (water + power + hazard) ...\n")
        result = SitingAgent().run()

        n = result["counties_scored"]
        self.stdout.write(self.style.SUCCESS(f"Scored {n} counties.\n"))

        latest = (
            SitingScore.objects.select_related("location")
            .order_by("rank")[:10]
        )
        self.stdout.write(self.style.SUCCESS("=== National top 10 (best sites) ==="))
        for s in latest:
            self.stdout.write(
                f"{s.rank:>2}. {s.location.county_name:<24} {s.location.metro:<28} "
                f"{s.suitability:>5.1f}  {s.grade:<10} "
                f"[W {s.water:>4.0f} | P {s.power:>4.0f} | H {s.hazard:>4.0f}]"
            )
        self.stdout.write(
            "\nColumns: W=water headroom, P=power availability, H=hazard safety (all 0-100, higher=better)."
        )
