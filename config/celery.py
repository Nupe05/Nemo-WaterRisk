"""Celery application + beat schedule for the nightly agent pipeline."""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("nemo")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Nightly build pipeline at 02:00, morning distribution sweep at 09:00.
app.conf.beat_schedule = {
    "nightly-data-refresh": {
        "task": "core.tasks.run_build_pipeline",
        "schedule": crontab(hour=2, minute=0),
    },
    "morning-distribution": {
        "task": "core.tasks.run_distribution_sweep",
        "schedule": crontab(hour=9, minute=0),
    },
}


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
