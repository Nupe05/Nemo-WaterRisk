"""Audience + pilot capture on the report page: newsletter signups and
free-read requests. Pure inbound lead capture — no approval gate."""
import pytest

from core.models import Lead, ReadRequest


@pytest.mark.django_db
def test_newsletter_subscribe_creates_lead(client):
    resp = client.post("/report/subscribe/", {"email": "buyer@example.com"})
    assert resp.status_code == 302
    assert "subscribed=1" in resp["Location"]
    lead = Lead.objects.get(email="buyer@example.com")
    assert lead.source == "newsletter"


@pytest.mark.django_db
def test_newsletter_subscribe_is_idempotent(client):
    for _ in range(3):
        client.post("/report/subscribe/", {"email": "dupe@example.com"})
    assert Lead.objects.filter(email="dupe@example.com", source="newsletter").count() == 1


@pytest.mark.django_db
def test_newsletter_rejects_bad_email(client):
    client.post("/report/subscribe/", {"email": "not-an-email"})
    assert Lead.objects.count() == 0


@pytest.mark.django_db
def test_request_read_creates_readrequest(client):
    resp = client.post(
        "/report/request/",
        {
            "name": "Dana Dev",
            "email": "dana@developer.com",
            "company": "BuildCo",
            "market": "Reno, NV",
            "note": "500MW, deciding this quarter",
        },
    )
    assert resp.status_code == 302
    assert "requested=1" in resp["Location"]
    rr = ReadRequest.objects.get(email="dana@developer.com")
    assert rr.name == "Dana Dev"
    assert rr.company == "BuildCo"
    assert rr.market == "Reno, NV"
    assert rr.status == ReadRequest.Status.NEW
    assert rr.source == "report_request"


@pytest.mark.django_db
def test_request_read_requires_valid_email(client):
    client.post("/report/request/", {"name": "No Email", "email": ""})
    assert ReadRequest.objects.count() == 0


@pytest.mark.django_db
def test_capture_urls_not_shadowed_by_site_report(client):
    # /report/subscribe/ and /report/request/ must hit the capture views, which
    # only accept POST (GET -> 405), not the site-report <str> route.
    assert client.get("/report/subscribe/").status_code == 405
    assert client.get("/report/request/").status_code == 405


@pytest.mark.django_db
def test_report_page_shows_capture_sections(client):
    from agents.siting_agent import SitingAgent
    SitingAgent().run()
    body = client.get("/report/").content.decode()
    assert "The Water Risk Monitor" in body
    assert "Request a free independent read" in body
    assert 'action="/report/subscribe/"' in body
    assert 'action="/report/request/"' in body
