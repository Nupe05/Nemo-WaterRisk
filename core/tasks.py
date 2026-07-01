"""Celery task entry points (referenced by the beat schedule in config.celery)."""
from celery import shared_task

from orchestrator import runner


@shared_task(name="core.tasks.run_build_pipeline")
def run_build_pipeline():
    return runner.build_pipeline()


@shared_task(name="core.tasks.run_distribution_sweep")
def run_distribution_sweep():
    return runner.distribution_sweep()
