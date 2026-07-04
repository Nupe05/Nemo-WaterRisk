"""Inbound email webhook: records, acknowledges, and queues an AI reply."""
import pytest

from core.models import ApprovalItem, InboundEmail, Lead


@pytest.mark.django_db
def test_inbound_records_acks_and_queues_reply(client, mailoutbox, monkeypatch):
    monkeypatch.setenv("INBOUND_EMAIL_TOKEN", "secret")
    import agents.llm_client as llm

    monkeypatch.setattr(
        llm, "call_llm_json",
        lambda *a, **k: {"reply": "Happy to help — details at https://www.nemowaterrisk.com."},
    )

    resp = client.post(
        "/inbound/email/?token=secret",
        {
            "from": "Jane Buyer <jane@datacorp.com>",
            "subject": "Question about Phoenix water risk",
            "text": "Can you share your methodology?",
        },
    )
    assert resp.status_code == 200

    inbound = InboundEmail.objects.get()
    assert inbound.from_email == "jane@datacorp.com"
    assert inbound.acknowledged is True
    assert Lead.objects.filter(email="jane@datacorp.com", source="inbound_email").exists()

    # instant acknowledgment auto-sent
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["jane@datacorp.com"]

    # AI reply queued for approval (not auto-sent)
    reply = ApprovalItem.objects.get(action_type=ApprovalItem.ActionType.EMAIL_REPLY)
    assert reply.state == ApprovalItem.State.PENDING
    assert reply.payload["to"] == "jane@datacorp.com"
    assert "nemowaterrisk.com" in reply.payload["body"]


@pytest.mark.django_db
def test_inbound_rejects_bad_token(client, monkeypatch):
    monkeypatch.setenv("INBOUND_EMAIL_TOKEN", "secret")
    resp = client.post("/inbound/email/?token=wrong", {"from": "a@b.com", "text": "hi"})
    assert resp.status_code == 403
    assert InboundEmail.objects.count() == 0


@pytest.mark.django_db
def test_email_reply_runner_sends_on_approval(mailoutbox):
    from agents.action_runner import execute_item

    item = ApprovalItem.objects.create(
        content_type="email_reply",
        action_type=ApprovalItem.ActionType.EMAIL_REPLY,
        state=ApprovalItem.State.APPROVED,
        payload={"to": "jane@datacorp.com", "subject": "Re: hi", "body": "Thanks for reaching out!"},
    )
    execute_item(item)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["jane@datacorp.com"]
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.EXECUTED
