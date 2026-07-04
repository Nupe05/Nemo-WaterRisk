"""The distribution sweep handles replies/reports but leaves social to the
drip-scheduler, so the two schedules don't race for the same approved rows."""
import pytest

from agents.distribution_agent import DistributionAgent
from core.models import ApprovalItem


@pytest.mark.django_db
def test_sweep_sends_email_reply_but_skips_social(mailoutbox):
    reply = ApprovalItem.objects.create(
        content_type="email_reply",
        action_type=ApprovalItem.ActionType.EMAIL_REPLY,
        state=ApprovalItem.State.APPROVED,
        payload={"to": "a@b.com", "subject": "Re: hi", "body": "Thanks!"},
    )
    tweet = ApprovalItem.objects.create(
        content_type="social_content",
        action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.APPROVED,
        payload={"thread": ["hello world"]},
    )

    DistributionAgent().run()

    reply.refresh_from_db()
    tweet.refresh_from_db()
    # the reply went out via the sweep …
    assert reply.state == ApprovalItem.State.EXECUTED
    assert len(mailoutbox) == 1
    # … but the tweet is untouched, left APPROVED for post_scheduled to drip.
    assert tweet.state == ApprovalItem.State.APPROVED
