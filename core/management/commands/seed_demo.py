"""Seed a demo watershed + site + sample data so you can exercise the pipeline
without any external API keys.

    python manage.py seed_demo
    python manage.py run_orchestrator --stage build
    # then approve items in /admin and:
    python manage.py run_orchestrator --stage distribute
"""
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import MonitoredSite, RawDataRecord, Watershed


class Command(BaseCommand):
    help = "Seed demo data (Phoenix-area watershed + data-center site)."

    def handle(self, *args, **options):
        ws, _ = Watershed.objects.get_or_create(
            huc_code="15060106",
            defaults={"name": "Salt River (Phoenix)"},
        )
        site, _ = MonitoredSite.objects.get_or_create(
            reference="PHX-DC-001",
            defaults={
                "name": "Phoenix Data Center Alpha",
                "location": Point(-112.074, 33.448),  # lon, lat
                "watershed": ws,
                "customer_id": "demo",
                "is_public_index": True,
            },
        )

        now = timezone.now()
        # Low streamflow + low precip to produce an elevated score.
        samples = [
            ("streamflow_cfs", 20.0, "ft3/s", RawDataRecord.Source.USGS),
            ("precip_mm", 5.0, "mm", RawDataRecord.Source.NOAA),
            ("epa_stress_proxy", 1.0, "count", RawDataRecord.Source.EPA),
        ]
        created = 0
        for i in range(5):
            for metric, value, unit, src in samples:
                RawDataRecord.objects.create(
                    source=src,
                    watershed=ws,
                    metric=metric,
                    value=value,
                    unit=unit,
                    observed_at=now - timedelta(days=i),
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded watershed={ws.huc_code} site={site.reference} records={created}"
            )
        )
