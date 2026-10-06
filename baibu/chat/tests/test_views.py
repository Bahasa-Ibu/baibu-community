import pytest
from django.urls import reverse

from baibu.chat import services
from baibu.chat.models import Conversation
from baibu.chat.models import Message
from baibu.chat.models import Run
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory

from .factories import ConversationFactory

pytestmark = pytest.mark.django_db

HOME = reverse("chat:home")
FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


@pytest.fixture
def chatter(client, user):
    record_consent(user=user, tier=ConsentRecord.Tier.NONE, source="test", scope="chat")
    client.force_login(user)
    return user


@pytest.fixture
def conversation(chatter):
    return services.start_conversation(user=chatter, language_code="en")


def _send(client, conversation, content="Hello there", key="k1", **extra):
    return client.post(
        reverse("chat:send", args=[conversation.pk]), {"content": content, "idempotency_key": key}, **extra
    )


def test_chat_requires_sign_in(client):
    response = client.get(HOME)
    assert response.status_code == 302
    assert reverse("account_login") in response.url


def test_first_visit_asks_for_chat_consent_then_returns(client, user):
    client.force_login(user)
    response = client.get(HOME)
    assert response.url == f"{reverse('chat:consent')}?next={HOME}"
    page = client.get(response.url).content.decode()
    assert "How may your conversations be used?" in page
    response = client.post(response.url, {"tier": ConsentRecord.Tier.EVAL_ONLY})
    assert response.url == HOME
    record = user.consent_records.get(scope="chat")
    assert record.tier == ConsentRecord.Tier.EVAL_ONLY
    assert record.metadata["consent_text_version"] == "1"
    # Platform consent is separate.
    assert not user.consent_records.filter(scope="platform").exists()
    assert client.get(HOME).status_code == 200


def test_consent_page_ignores_unsafe_next_and_unchanged_choice(client, chatter):
    response = client.post(f"{reverse('chat:consent')}?next=https://evil.example.com/", {"tier": "none"})
    assert response.url == HOME
    assert chatter.consent_records.filter(scope="chat").count() == 1


def test_choosing_none_still_allows_chatting(client, chatter):
    content = client.get(HOME).content.decode()
    assert "Start a conversation" in content


def test_new_conversation_sends_first_message(client, chatter, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("chat:new"), {"content": "Good morning", "idempotency_key": "first"})
    conversation = Conversation.objects.get()
    assert response.url == reverse("chat:conversation", args=[conversation.pk])
    assert conversation.consent_tier == ConsentRecord.Tier.NONE
    page = client.get(response.url).content.decode()
    assert "You said: Good morning" in page
    # The same form posted twice opens the same conversation.
    again = client.post(reverse("chat:new"), {"content": "Good morning", "idempotency_key": "first"})
    assert again.url == response.url
    assert Conversation.objects.count() == 1


def test_new_conversation_needs_text(client, chatter):
    response = client.post(reverse("chat:new"), {"content": "   ", "idempotency_key": "x"})
    assert response.status_code == 400
    assert not Conversation.objects.exists()


def test_send_with_fetch_returns_fragment_and_polls(client, conversation):
    response = _send(client, conversation, **FETCH)
    assert response.status_code == 200
    assert response["X-Chat-Pending"] == "1"
    assert response["X-Chat-Next-Key"]
    assert "Writing a reply" in response.content.decode()
    services.execute(Run.objects.get().pk)
    poll = client.get(reverse("chat:messages", args=[conversation.pk]), **FETCH)
    assert poll["X-Chat-Pending"] == "0"
    assert "You said: Hello there" in poll.content.decode()


def test_send_without_javascript_redirects(client, conversation):
    response = _send(client, conversation)
    assert response.url == reverse("chat:conversation", args=[conversation.pk])
    assert Message.objects.count() == 1


def test_send_errors(client, conversation, settings):
    settings.CHAT_MAX_MESSAGE_CHARACTERS = 5
    response = _send(client, conversation, content="far too long", **FETCH)
    assert response.status_code == 400
    assert "at most 5 characters" in response.content.decode()
    settings.CHAT_MAX_MESSAGE_CHARACTERS = 4000
    _send(client, conversation)
    busy = _send(client, conversation, key="k2", **FETCH)
    assert "wait for the reply" in busy.content.decode()
    busy_plain = _send(client, conversation, key="k3", follow=True)
    assert "wait for the reply" in busy_plain.content.decode()


def test_failed_reply_offers_retry(client, conversation, settings):
    settings.CHAT_MAX_ATTEMPTS = 2
    _send(client, conversation, content="[mock-fail]")
    run = Run.objects.get()
    services.execute(run.pk)
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert "No reply could be generated." in page
    assert reverse("chat:retry", args=[run.pk]) in page
    response = client.post(reverse("chat:retry", args=[run.pk]), **FETCH)
    assert response["X-Chat-Pending"] == "1"
    retry = Run.objects.get(attempt=2)
    services.execute(retry.pk)
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    # The limit is reached: no more retry button.
    assert reverse("chat:retry", args=[retry.pk]) not in page
    refused = client.post(reverse("chat:retry", args=[retry.pk]), follow=True)
    assert "too many times" in refused.content.decode()
    refused = client.post(reverse("chat:retry", args=[retry.pk]), **FETCH)
    assert refused.status_code == 400


def test_retry_without_javascript_redirects(client, conversation):
    _send(client, conversation, content="[mock-fail]")
    run = Run.objects.get()
    services.execute(run.pk)
    response = client.post(reverse("chat:retry", args=[run.pk]))
    assert response.url == reverse("chat:conversation", args=[conversation.pk])


def test_conversations_are_private(client, chatter):
    other = ConversationFactory(user=UserFactory())
    for name in ("chat:conversation", "chat:messages"):
        assert client.get(reverse(name, args=[other.pk])).status_code == 404
    for name in ("chat:send", "chat:delete"):
        assert client.post(reverse(name, args=[other.pk])).status_code == 404


def test_sidebar_lists_own_conversations(client, conversation):
    _send(client, conversation, content="About the harvest")
    ConversationFactory(user=UserFactory(), title="Someone else's chat")
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert "About the harvest" in page
    assert "Someone else" not in page


def test_delete_conversation(client, conversation):
    _send(client, conversation)
    response = client.post(reverse("chat:delete", args=[conversation.pk]))
    assert response.url == HOME
    assert not Conversation.objects.exists()
    assert not Message.objects.exists()


def test_chat_can_be_switched_off(client, chatter, settings):
    settings.CHAT_ENABLED = False
    assert client.get(HOME).status_code == 404
    assert reverse("chat:home") not in client.get(reverse("home")).content.decode()
