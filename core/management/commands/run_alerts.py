"""Run the monitoring alert sweep: draft approval-gated alerts for subscribers
whose watched site or metro has moved adversely.

Safe to run unattended — it only queues approval items; nothing emails until you
approve. Wire to Heroku Scheduler right after `daily_refresh` and `score_siting`
so alerts reflect the freshest scores.

    python manage.py run_alerts
"""
from django.core.management.base import BaseCommand

from agents.monitor_agent import MonitorAgent


class Command(BaseCommand):
    help = "Draft approval-gated alerts for subscriptions with adverse risk moves."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500, help="Max alerts to queue this run.")

    def handle(self, *args, **options):
        result = MonitorAgent().run(limit=max(1, options["limit"]))
        self.stdout.write(
            self.style.SUCCESS(
                f"run_alerts complete: checked={result['checked']} "
                f"alerts_queued={result['alerts_queued']} (pending in /admin approval queue)"
            )
        )
