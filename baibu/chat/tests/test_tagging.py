import json
from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from baibu.chat import llm
from baibu.chat import services
from baibu.chat import tagging
from baibu.chat.models import Conversation
from baibu.chat.models import ConversationTag
from baibu.chat.models import ModelVariant
from baibu.chat.models import Topic
from baibu.chat.tasks import tag_conversations
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord

pytestmark = pytest.mark.django_db


@pytest.fixture
def tagging_on(settings):
    settings.CHAT_TAGGING_ENABLED = True
    settings.CHAT_TAGGING_IDLE_MINUTES = 30
    return settings


@pytest.fixture
def topics():
    return [
        Topic.objects.create(slug="farming", label="Farming", description="Crops, seeds, soil"),
        Topic.objects.create(slug="market-days", label="Market days"),
        Topic.objects.create(slug="retired", label="Retired topic", active=False),
    ]


def _conversation(user, text, *, tier=ConsentRecord.Tier.EVAL_ONLY, idle_minutes=60):
    record_consent(user=user, tier=tier, source="test", scope="chat")
    conversation = services.start_conversation(user=user, language_code="en")
    _message, run = services.send_message(conversation=conversation, content=text, idempotency_key=text[:60])
    services.execute(run.pk)
    Conversation.objects.filter(pk=conversation.pk).update(
        last_activity_at=timezone.now() - timedelta(minutes=idle_minutes)
    )
    conversation.refresh_from_db()
    return conversation


def _model_answer(payload):
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return mock.patch("baibu.chat.llm.complete", return_value=llm.Completion(content=content, model="m"))


def test_off_by_default(user, topics):
    _conversation(user, "When are market days?")
    assert tag_conversations() == 0
    assert not ConversationTag.objects.exists()


def test_mock_model_tags_by_keywords(tagging_on, user, topics):
    conversation = _conversation(user, "Which seeds suit farming here? And when are market days?")
    assert tag_conversations() == 1
    tag = conversation.tag
    assert sorted(t.slug for t in tag.topics.all()) == ["farming", "market-days"]
    assert (tag.language, tag.intent, tag.tagger, tag.error) == ("en", "question", "keywords", "")
    assert str(tag).startswith("Tags for")
    # Nothing new since: not tagged again.
    assert tag_conversations() == 0


def test_inactive_topics_and_statements(tagging_on, user, topics):
    conversation = _conversation(user, "Just saying hello about my retired topic")
    tag = tagging.tag_conversation(conversation)
    assert list(tag.topics.all()) == []
    assert tag.intent == "conversation"


def test_new_activity_triggers_retagging(tagging_on, user, topics):
    conversation = _conversation(user, "Tell me about farming")
    tag_conversations()
    _message, run = services.send_message(conversation=conversation, content="And market days?", idempotency_key="2")
    services.execute(run.pk)
    # Not idle yet.
    assert tag_conversations() == 0
    Conversation.objects.filter(pk=conversation.pk).update(last_activity_at=timezone.now() - timedelta(hours=1))
    assert tag_conversations() == 1
    assert ConversationTag.objects.count() == 1
    assert "market-days" in {t.slug for t in ConversationTag.objects.get().topics.all()}


def test_consent_below_the_minimum_is_never_tagged(tagging_on, user, topics):
    _conversation(user, "farming", tier=ConsentRecord.Tier.NONE)
    assert tag_conversations() == 0
    tagging_on.CHAT_TAGGING_MIN_TIER = "none"
    assert tag_conversations() == 1


def test_batch_size(tagging_on, user, topics):
    tagging_on.CHAT_TAGGING_BATCH_SIZE = 1
    _conversation(user, "farming one")
    _conversation(user, "farming two")
    assert tag_conversations() == 1
    assert tag_conversations() == 1
    assert tag_conversations() == 0


def test_model_tagger_reads_json(tagging_on, user, topics):
    ModelVariant.objects.create(name="main", model="openai/example", is_default=True)
    conversation = _conversation(user, "Something about crops")
    answer = {"topics": ["farming", "farming", "unknown", "retired"], "language": "sw", "intent": "advice"}
    with _model_answer(answer) as complete:
        tag = tagging.tag_conversation(conversation)
    prompt = complete.call_args.args[1][0]["content"]
    assert "- farming: Farming, Crops, seeds, soil" in prompt
    assert "retired" not in prompt
    assert "User: Something about crops" in complete.call_args.args[1][1]["content"]
    assert [t.slug for t in tag.topics.all()] == ["farming"]
    assert (tag.language, tag.intent, tag.tagger) == ("sw", "advice", "openai/example")


def test_model_tagger_limits_and_cleans(tagging_on, user, topics):
    tagging_on.CHAT_TAGGING_MODEL = "openai/tagger"
    tagging_on.CHAT_TAGGING_MAX_TOPICS = 1
    conversation = _conversation(user, "x")
    with _model_answer('```json\n{"topics": ["market-days", "farming"], "intent": "shouting"}\n```'):
        tag = tagging.tag_conversation(conversation)
    assert [t.slug for t in tag.topics.all()] == ["market-days"]
    assert (tag.intent, tag.language, tag.tagger) == ("", "", "openai/tagger")


@pytest.mark.parametrize("answer", ["no json here", "[1, 2]", '{"topics": "farming"}'])
def test_model_tagger_bad_answers(tagging_on, user, topics, answer):
    tagging_on.CHAT_TAGGING_MODEL = "openai/tagger"
    conversation = _conversation(user, "x")
    with _model_answer(answer):
        tag = tagging.tag_conversation(conversation)
    if answer.startswith('{"topics"'):
        assert tag.error == ""
        assert list(tag.topics.all()) == []
    else:
        assert tag.error.startswith("Tagger answer")


def test_model_failure_is_recorded_and_not_retried_until_new_activity(tagging_on, user, topics):
    tagging_on.CHAT_TAGGING_MODEL = "openai/tagger"
    conversation = _conversation(user, "x")
    with mock.patch("baibu.chat.llm.complete", side_effect=llm.ModelError("down", code="timeout")):
        assert tag_conversations() == 1
    tag = ConversationTag.objects.get(conversation=conversation)
    assert tag.error == "down"
    assert tag_conversations() == 0


def test_transcript_is_bounded(tagging_on, user, settings):
    settings.CHAT_TAGGING_MAX_CHARACTERS = 20
    conversation = _conversation(user, "A long message about many things")
    assert tagging.transcript(conversation) == "User: A long message"


def test_admin_shows_tags_and_manages_topics(client, admin_user, tagging_on, user, topics):
    conversation = _conversation(user, "farming")
    assert tag_conversations() == 1
    assert [t.slug for t in conversation.tag.topics.all()] == ["farming"]
    client.force_login(admin_user)
    page = client.get(reverse("admin:chat_conversation_change", args=[conversation.pk])).content.decode()
    assert "Farming" in page
    assert client.get(reverse("admin:chat_conversation_changelist") + "?tag__topics__id__exact=1").status_code == 200
    assert client.get(reverse("admin:chat_topic_changelist")).status_code == 200
    client.post(reverse("admin:chat_topic_add"), {"label": "Health", "slug": "health", "active": "on"})
    assert Topic.objects.filter(slug="health").exists()
    assert str(Topic.objects.get(slug="health")) == "Health"
