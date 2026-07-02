"""The premium site report is staff-only and renders the score + branding."""
import pytest
from django.contrib.gis.geos import Point

from core.models import MonitoredSite, Watershed, WaterRiskScore


@pytest.fixture
def site(db):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River", usgs_site_no="09498500")
    s = MonitoredSite.objects.create(
        reference="PHX-DC-001", name="Phoenix", location=Point(-112.0, 33.0),
        watershed=ws, is_public_index=True,
    )
    WaterRiskScore.objects.create(
        watershed=ws, score=61.5,
        components={"streamflow_deficit": 74.9, "precip_deficit": 0.0, "withdrawal_pressure": 10.0},
    )
    return s


@pytest.mark.django_db
def test_report_requires_staff(client, site):
    # Anonymous users are redirected (to the admin login), never shown the report.
    resp = client.get("/report/PHX-DC-001/")
    assert resp.status_code == 302


@pytest.mark.django_db
def test_report_renders_for_staff(client, django_user_model, site):
    user = django_user_model.objects.create_user("staff", password="x", is_staff=True)
    client.force_login(user)
    resp = client.get("/report/PHX-DC-001/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Confidential Site Risk Report" in body
    assert "61.5" in body
    assert "Streamflow deficit" in body
