import pytest
from django.urls import reverse

from baibu.chat import services
from baibu.chat.models import ModelVariant
from baibu.chat.models import Prompt
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    admin = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(admin)
    return admin


def test_adding_prompts_creates_versions_and_switches_active(client, staff):
    url = reverse("admin:chat_prompt_add")
    client.post(url, {"name": "system", "body": "First", "notes": "", "active": "on"})
    client.post(url, {"name": "system", "body": "Second", "notes": "shorter", "active": "on"})
    first, second = Prompt.objects.order_by("version")
    assert (first.version, second.version) == (1, 2)
    assert (first.active, second.active) == (False, True)
    assert second.created_by == staff
    # Existing versions show their body read-only.
    page = client.get(reverse("admin:chat_prompt_change", args=[first.pk])).content.decode()
    assert "First" in page
    assert 'name="body"' not in page


def test_activate_action(client, staff):
    first = Prompt.objects.create(name="system", body="One", active=True)
    second = Prompt.objects.create(name="system", body="Two")
    changelist = reverse("admin:chat_prompt_changelist")
    response = client.post(changelist, {"action": "activate", "_selected_action": [first.pk, second.pk]}, follow=True)
    assert "Select exactly one version." in response.content.decode()
    client.post(changelist, {"action": "activate", "_selected_action": [second.pk]})
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.active, second.active) == (False, True)


def test_only_one_default_model(client, staff):
    url = reverse("admin:chat_modelvariant_add")
    for name in ("a", "b"):
        client.post(
            url,
            {"name": name, "model": "mock", "api_base": "", "api_key_env": "", "parameters": "{}", "is_default": "on"},
        )
    assert list(ModelVariant.objects.order_by("name").values_list("name", "is_default")) == [("a", False), ("b", True)]


def test_conversations_and_runs_are_read_only(client, staff, user):
    conversation = services.start_conversation(user=user)
    services.send_message(conversation=conversation, content="Hi", idempotency_key="k")
    page = client.get(reverse("admin:chat_conversation_change", args=[conversation.pk]))
    assert page.status_code == 200
    assert "Hi" in page.content.decode()
    assert "run_queued" in page.content.decode()
    response = client.post(reverse("admin:chat_conversation_change", args=[conversation.pk]), {})
    assert response.status_code == 403
    run = conversation.runs.get()
    assert client.get(reverse("admin:chat_run_change", args=[run.pk])).status_code == 200
    assert client.post(reverse("admin:chat_run_change", args=[run.pk]), {}).status_code == 403
    assert client.get(reverse("admin:chat_run_add")).status_code == 403
    assert client.get(reverse("admin:chat_conversation_add")).status_code == 403
