"""The seed_metros command should publish the data-center metros to the index."""
import pytest
from django.core.management import call_command

from core.models import MonitoredSite, Watershed


@pytest.mark.django_db
def test_seed_metros_creates_public_sites():
    call_command("seed_metros")
    public = MonitoredSite.objects.filter(is_public_index=True)
    assert public.count() == 5
    # every metro has a watershed with a USGS gauge attached
    for site in public:
        assert site.watershed is not None
        assert site.watershed.usgs_site_no


@pytest.mark.django_db
def test_seed_metros_is_idempotent():
    call_command("seed_metros")
    call_command("seed_metros")
    assert MonitoredSite.objects.filter(is_public_index=True).count() == 5
    assert Watershed.objects.count() == 5
