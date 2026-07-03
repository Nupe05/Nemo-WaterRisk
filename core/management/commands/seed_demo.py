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
            huc_code="15060103",
            defaults={
                "name": "Salt River (Roosevelt)",
                # Real, long-running USGS gauge: SALT RIVER NEAR ROOSEVELT, AZ.
                "usgs_site_no": "09498500",
                "county_fips": "04013",  # Maricopa County, AZ (Phoenix metro)
            },
        )
        if not ws.usgs_site_no or not ws.county_fips:
            ws.usgs_site_no = "09498500"
            ws.county_fips = "04013"
            ws.save(update_fields=["usgs_site_no", "county_fips"])
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
        # Realistic offline sample (mirrors live values seen for this gauge):
        # current flow well below the historical median -> elevated risk.
        samples = [
            ("streamflow_cfs", 39.0, "ft3/s", RawDataRecord.Source.USGS),
            ("streamflow_median_cfs", 157.0, "ft3/s", RawDataRecord.Source.USGS),
            ("drought_index", 0.6, "dsci_frac", RawDataRecord.Source.USDM),
            ("population", 4_420_568.0, "people", RawDataRecord.Source.CENSUS),  # Maricopa 2020
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
