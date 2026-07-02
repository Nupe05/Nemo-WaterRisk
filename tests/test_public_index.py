"""Tests for the public Water Risk Index pages and lead capture."""
import pytest
from django.contrib.gis.geos import Point

from core.models import Lead, MonitoredSite, Watershed, WaterRiskScore


@pytest.fixture
def public_site(db):
    ws = Watershed.objects.create(huc_code="15060103", name="Salt River", usgs_site_no="09498500")
    site = MonitoredSite.objects.create(
        reference="PHX-DC-001",
        name="Phoenix Data Center Alpha",
        location=Point(-112.074, 33.448),
        watershed=ws,
        is_public_index=True,
    )
    WaterRiskScore.objects.create(
        watershed=ws, score=67.0, components={"streamflow_deficit": 74.9, "precip_deficit": 30.0}
    )
    return site


@pytest.mark.django_db
def test_index_page_renders(client, public_site):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Water Risk Index" in body
    assert "Phoenix Data Center Alpha" in body
    assert "67" in body  # the score appears


@pytest.mark.django_db
def test_detail_page_renders(client, public_site):
    resp = client.get("/site/PHX-DC-001/")
    assert resp.status_code == 200
    assert "What drives this score" in resp.content.decode()


@pytest.mark.django_db
def test_detail_404_for_non_public(client):
    Watershed.objects.create(huc_code="00000000", name="Hidden")
    MonitoredSite.objects.create(
        reference="SECRET-1", name="Private", location=Point(0, 0), is_public_index=False
    )
    assert client.get("/site/SECRET-1/").status_code == 404


@pytest.mark.django_db
def test_subscribe_creates_lead(client, public_site):
    resp = client.post("/subscribe/", {"email": "buyer@datacorp.com", "site_ref": "PHX-DC-001"})
    assert resp.status_code == 302
    lead = Lead.objects.get(email="buyer@datacorp.com")
    assert lead.site_ref == "PHX-DC-001"
    assert lead.source == "water_risk_index"


@pytest.mark.django_db
def test_subscribe_rejects_bad_email(client):
    client.post("/subscribe/", {"email": "not-an-email"})
    assert Lead.objects.count() == 0


@pytest.mark.django_db
def test_api_sites_json(client, public_site):
    resp = client.get("/api/sites/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["sites"][0]["band"] == "High"  # 67 -> High
