import pytest
from django.urls import reverse

from baibu.chat import services
from baibu.chat.models import ChatFlag
from baibu.chat.models import Message
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def reply(client, user):
    record_consent(user=user, tier=ConsentRecord.Tier.NONE, source="test", scope="chat")
    client.force_login(user)
    conversation = services.start_conversation(user=user)
    _message, run = services.send_message(conversation=conversation, content="Hello", idempotency_key="k")
    return services.execute(run.pk).reply


def test_reply_shows_a_report_link(client, reply):
    page = client.get(reverse("chat:conversation", args=[reply.conversation_id])).content.decode()
    assert reverse("chat:report", args=[reply.pk]) in page


def test_report_a_reply(client, reply):
    url = reverse("chat:report", args=[reply.pk])
    assert "What is wrong with this reply?" in client.get(url).content.decode()
    response = client.post(url, {"reason": "incorrect", "note": " The bus does not run on Sundays. "})
    assert response.url == reverse("chat:conversation", args=[reply.conversation_id])
    flag = ChatFlag.objects.get()
    assert (flag.reason, flag.note, flag.status) == ("incorrect", "The bus does not run on Sundays.", "open")
    assert reply.conversation.events.filter(type="reply_reported").exists()
    # Reporting again does not add a second report.
    client.post(url, {"reason": "harmful"})
    assert ChatFlag.objects.count() == 1
    assert str(flag) == "Wrong or misleading (Open)"


def test_report_needs_a_reason(client, reply):
    response = client.post(reverse("chat:report", args=[reply.pk]), {"note": "x"})
    assert response.status_code == 200
    assert not ChatFlag.objects.exists()


def test_only_own_assistant_replies_can_be_reported(client, reply):
    question = reply.conversation.messages.get(role=Message.Role.USER)
    assert client.get(reverse("chat:report", args=[question.pk])).status_code == 404
    with pytest.raises(services.ChatError):
        services.report_message(message=question, user=reply.conversation.user, reason="other")
    with pytest.raises(services.ChatError):
        services.report_message(message=reply, user=UserFactory(), reason="other")


def test_decide_once_and_notify_reporter(reply, admin_user):
    flag = services.report_message(message=reply, user=reply.conversation.user, reason="harmful")
    assert services.decide_flag(flag, ChatFlag.Status.DISMISSED, reviewer=admin_user, note=" fine ") is True
    assert (flag.status, flag.decided_by, flag.decision_note) == ("dismissed", admin_user, "fine")
    assert services.decide_flag(flag, ChatFlag.Status.CONFIRMED, reviewer=admin_user) is False
    note = reply.conversation.user.notifications.get()
    assert note.display_title == "Your report was reviewed"
    with pytest.raises(ValueError, match="Not a decision"):
        services.decide_flag(flag, ChatFlag.Status.OPEN, reviewer=admin_user)


def test_flag_admin_is_read_only(client, reply, admin_user):
    flag = services.report_message(message=reply, user=reply.conversation.user, reason="harmful")
    client.force_login(admin_user)
    url = reverse("admin:chat_chatflag_change", args=[flag.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {}).status_code == 403
    assert client.get(reverse("admin:chat_chatflag_add")).status_code == 403
