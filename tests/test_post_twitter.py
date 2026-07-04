"""X/Twitter posting: chains a thread, and fails clearly without credentials."""
import pytest

from agents.action_runner import ActionError, execute_item
from core.models import ApprovalItem

X_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


class _Resp:
    def __init__(self, tid):
        self.data = {"id": tid}


class _FakeClient:
    calls: list = []

    def __init__(self, **kwargs):
        pass

    def create_tweet(self, text, in_reply_to_tweet_id=None):
        _FakeClient.calls.append({"text": text, "reply_to": in_reply_to_tweet_id})
        return _Resp(len(_FakeClient.calls))


@pytest.mark.django_db
def test_post_twitter_publishes_thread(monkeypatch):
    for k in X_KEYS:
        monkeypatch.setenv(k, "test-" + k)
    import tweepy

    _FakeClient.calls = []
    monkeypatch.setattr(tweepy, "Client", _FakeClient)

    item = ApprovalItem.objects.create(
        content_type="social_content",
        action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.APPROVED,
        payload={"thread": ["first post", "second post", "third post"]},
    )
    execute_item(item)
    item.refresh_from_db()

    assert item.state == ApprovalItem.State.EXECUTED
    assert len(_FakeClient.calls) == 3
    assert _FakeClient.calls[0]["reply_to"] is None       # root tweet
    assert _FakeClient.calls[1]["reply_to"] == 1          # replies chain the thread
    assert _FakeClient.calls[2]["reply_to"] == 2
    assert item.result["tweet_ids"] == [1, 2, 3]


@pytest.mark.django_db
def test_post_twitter_requires_credentials(monkeypatch):
    for k in X_KEYS:
        monkeypatch.delenv(k, raising=False)
    item = ApprovalItem.objects.create(
        content_type="social_content",
        action_type=ApprovalItem.ActionType.POST_TWITTER,
        state=ApprovalItem.State.APPROVED,
        payload={"thread": ["hello"]},
    )
    with pytest.raises(ActionError):
        execute_item(item)
    item.refresh_from_db()
    assert item.state == ApprovalItem.State.FAILED
