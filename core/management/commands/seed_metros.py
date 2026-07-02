"""Seed the public index with the major U.S. data-center metros.

Each metro is tied to a real, active USGS streamflow gauge (verified live), so
the pipeline can score them from public data. Idempotent — safe to re-run.

    python manage.py seed_metros
    python manage.py run_orchestrator --stage build   # then score them all
"""
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from core.models import MonitoredSite, Watershed

# (huc8, watershed_name, usgs_site_no, site_reference, site_name, lon, lat)
METROS = [
    ("02070008", "Potomac River (Washington, DC)", "01646500",
     "IAD-DC-001", "Ashburn / Northern Virginia", -77.1276, 38.9498),
    ("12030105", "Trinity River (Dallas)", "08057000",
     "DFW-DC-001", "Dallas–Fort Worth", -96.8219, 32.7749),
    ("15060103", "Salt River (Roosevelt)", "09498500",
     "PHX-DC-001", "Phoenix", -110.9221, 33.6192),
    ("17070105", "Columbia River (The Dalles)", "14105700",
     "DLS-DC-001", "The Dalles, Oregon", -121.1899, 45.6083),
    ("03130001", "Chattahoochee River (Atlanta)", "02336000",
     "ATL-DC-001", "Atlanta", -84.4544, 33.8592),
]


class Command(BaseCommand):
    help = "Seed the public Water Risk Index with major data-center metros (real USGS gauges)."

    def handle(self, *args, **options):
        new_sites = 0
        for huc, wname, site_no, ref, sname, lon, lat in METROS:
            ws, _ = Watershed.objects.get_or_create(
                huc_code=huc, defaults={"name": wname, "usgs_site_no": site_no}
            )
            # Make sure the gauge is set even if the watershed already existed.
            if ws.usgs_site_no != site_no:
                ws.usgs_site_no = site_no
                ws.save(update_fields=["usgs_site_no"])

            site, created = MonitoredSite.objects.get_or_create(
                reference=ref,
                defaults={
                    "name": sname,
                    "location": Point(lon, lat),
                    "watershed": ws,
                    "is_public_index": True,
                },
            )
            if not created and not (site.is_public_index and site.watershed_id == ws.id):
                site.watershed = ws
                site.is_public_index = True
                site.save(update_fields=["watershed", "is_public_index"])
            new_sites += 1 if created else 0

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(METROS)} data-center metros ({new_sites} new). "
                f"Run: python manage.py run_orchestrator --stage build"
            )
        )
