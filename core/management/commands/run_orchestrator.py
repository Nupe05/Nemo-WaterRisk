"""Run an orchestrator stage from the CLI (cron-friendly alternative to Celery).

Examples
--------
    python manage.py run_orchestrator --stage build
    python manage.py run_orchestrator --stage distribute
"""
from django.core.management.base import BaseCommand

from orchestrator import runner


class Command(BaseCommand):
    help = "Run an orchestrator stage (build | distribute)."

    def add_arguments(self, parser):
        parser.add_argument("--stage", choices=["build", "distribute"], required=True)
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        stage = options["stage"]
        if stage == "build":
            result = runner.build_pipeline()
        else:
            result = runner.distribution_sweep(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"{stage} complete: {result}"))
