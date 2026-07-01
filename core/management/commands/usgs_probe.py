"""Live sanity check against the real USGS API (no database writes).

    python manage.py usgs_probe                 # default: Salt River @ Roosevelt
    python manage.py usgs_probe --site 09512500

Pulls current streamflow + the historical median for today, computes the
streamflow-deficit component and an indicative risk score, and prints it.
Great for confirming the pipeline sees real data before wiring the full run.
"""
from django.core.management.base import BaseCommand

from integrations import usgs
from scoring.model import ScoreInputs, compute_score, streamflow_deficit


class Command(BaseCommand):
    help = "Probe the live USGS API for a gauge and print an indicative risk score."

    def add_arguments(self, parser):
        parser.add_argument("--site", default="09498500", help="USGS site number")

    def handle(self, *args, **options):
        site = options["site"]
        self.stdout.write(f"Querying USGS for site {site} ...")

        latest = usgs.fetch_latest_by_sites([site])
        if not latest:
            self.stderr.write(self.style.ERROR("No current streamflow returned for that site."))
            return
        flow = latest[0]["value"]
        median = usgs.median_for_date(site)

        self.stdout.write(f"  current streamflow : {flow:.1f} ft3/s")
        if median is None:
            self.stdout.write("  historical median  : (unavailable)")
            self.stdout.write(self.style.WARNING("Cannot compute deficit without a baseline."))
            return
        self.stdout.write(f"  historical median  : {median:.1f} ft3/s (today, day-of-year)")

        deficit = streamflow_deficit(flow, median)
        result = compute_score(ScoreInputs(streamflow_deficit=deficit))
        self.stdout.write(f"  streamflow deficit : {deficit * 100:.0f}%")
        self.stdout.write(
            self.style.SUCCESS(
                f"  indicative risk (streamflow component only): {result['score']:.0f}/100"
            )
        )
        self.stdout.write(
            "Note: full score also folds in precipitation and withdrawal pressure."
        )
