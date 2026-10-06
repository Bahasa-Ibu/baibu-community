from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from baibu.chat import llm
from baibu.chat import services
from baibu.chat.models import ConversationEvent
from baibu.chat.models import Message
from baibu.chat.models import ModelVariant
from baibu.chat.models import Prompt
from baibu.chat.models import Run
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord
from baibu.users.models import ImmutableRecordError

from .factories import ConversationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation(user):
    record_consent(user=user, tier=ConsentRecord.Tier.TRAINING_ELIGIBLE, source="test", scope="chat")
    return services.start_conversation(user=user, language_code="en")


def _send(conversation, content="Hello there", key="k1"):
    return services.send_message(conversation=conversation, content=content, idempotency_key=key)


def _events(conversation):
    return list(conversation.events.values_list("type", flat=True))


def test_start_records_chat_consent(conversation):
    assert conversation.consent_tier == ConsentRecord.Tier.TRAINING_ELIGIBLE
    assert _events(conversation) == ["conversation_started"]


def test_send_creates_message_run_and_title(conversation, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        message, run = _send(conversation, content="  Where can I buy seeds?\nAnd soil?  ")
    conversation.refresh_from_db()
    assert message.content == "Where can I buy seeds?\nAnd soil?"
    assert run.status == Run.Status.QUEUED
    assert run.triggering_message == message
    assert conversation.title == "Where can I buy seeds?"
    assert _events(conversation)[-2:] == ["message_sent", "run_queued"]
    assert len(callbacks) == 1


def test_send_is_idempotent(conversation):
    first = _send(conversation)
    assert _send(conversation) == first
    assert Message.objects.count() == 1
    assert Run.objects.count() == 1


def test_send_while_a_reply_is_pending_is_refused(conversation):
    _send(conversation)
    with pytest.raises(services.ConversationBusyError):
        _send(conversation, key="k2")


def test_execute_with_mock_model_writes_reply(conversation):
    _message, run = _send(conversation)
    run = services.execute(run.pk)
    assert run.status == Run.Status.COMPLETED
    assert run.model_name == "mock"
    assert run.prompt_version == "built-in"
    assert run.reply.content == "You said: Hello there"
    assert run.started_at
    assert run.completed_at
    assert _events(conversation)[-2:] == ["run_started", "run_completed"]
    # A second execution of the same run does nothing.
    assert services.execute(run.pk) is None


def test_execute_uses_default_variant_and_active_prompt(conversation, settings):
    ModelVariant.objects.create(name="main", model="mock", is_default=True)
    prompt = Prompt.objects.create(name="system", body="Be brief, {{ user_name }}. {{ platform.name }}.", active=True)
    _message, run = _send(conversation)
    with mock.patch("baibu.chat.llm.complete", wraps=llm.complete) as complete:
        run = services.execute(run.pk)
    messages = complete.call_args.args[1]
    assert messages[0] == {
        "role": "system",
        "content": f"Be brief, {conversation.user.name}. {settings.PLATFORM_NAME}.",
    }
    assert run.prompt == prompt
    assert run.prompt_version == "system v1"
    assert run.model_variant.name == "main"


def test_built_in_prompt_names_the_platform_and_language(conversation, settings):
    text = services.render_system_prompt(conversation, None)
    assert settings.PLATFORM_NAME in text
    assert "English" in text
    conversation.language_code = "xx-unknown"
    assert "xx-unknown" in services.render_system_prompt(conversation, None)


def test_context_is_limited_and_ends_with_the_triggering_message(conversation, settings):
    settings.CHAT_CONTEXT_MESSAGES = 3
    for n in range(3):
        _message, run = _send(conversation, content=f"message {n}", key=f"k{n}")
        services.execute(run.pk)
    _message, run = _send(conversation, content="last", key="k-last")
    messages = services.build_messages(run, "SYSTEM")
    assert [m["content"] for m in messages] == ["SYSTEM", "message 2", "You said: message 2", "last"]


def test_model_failure_fails_the_run(conversation):
    _message, run = _send(conversation, content="please [mock-fail]")
    run = services.execute(run.pk)
    assert run.status == Run.Status.FAILED
    assert run.error["code"] == "mock_failure"
    assert not Message.objects.filter(role=Message.Role.ASSISTANT).exists()
    assert _events(conversation)[-1] == "run_failed"


def test_unexpected_error_fails_the_run(conversation):
    _message, run = _send(conversation)
    with mock.patch("baibu.chat.services.build_messages", side_effect=KeyError("x")):
        run = services.execute(run.pk)
    assert run.error == {"code": "internal_error", "message": "KeyError"}


def test_empty_reply_fails_the_run(conversation):
    _message, run = _send(conversation)
    with mock.patch("baibu.chat.llm.complete", return_value=llm.Completion(content="  ", model="m")):
        run = services.execute(run.pk)
    assert run.error["code"] == "empty_response"


def test_retry_after_failure(conversation):
    """TC-CHT-01: a timeout, then a successful retry, with one user message."""
    _message, run = _send(conversation)
    with mock.patch("baibu.chat.llm.complete", side_effect=llm.ModelError("slow", code="timeout")):
        services.execute(run.pk)
    retry = services.retry_run(run)
    assert retry.attempt == 2
    assert retry.triggering_message == run.triggering_message
    with mock.patch("baibu.chat.llm.complete", return_value=llm.Completion(content="Hello", model="m")):
        services.execute(retry.pk)
    assert Run.objects.get(pk=run.pk).error["code"] == "timeout"
    assert list(conversation.messages.values_list("role", "content")) == [
        ("user", "Hello there"),
        ("assistant", "Hello"),
    ]
    # Retrying the old failed run again returns the newer attempt.
    assert services.retry_run(Run.objects.get(pk=run.pk)) == retry


def test_retries_stop_at_the_limit(conversation, settings):
    """TC-CHT-02."""
    settings.CHAT_MAX_ATTEMPTS = 2
    _message, run = _send(conversation, content="[mock-fail]")
    services.execute(run.pk)
    retry = services.retry_run(run)
    services.execute(retry.pk)
    with pytest.raises(services.RetryNotAllowedError, match="too many"):
        services.retry_run(Run.objects.get(pk=retry.pk))
    assert Run.objects.count() == 2
    assert not Message.objects.filter(role=Message.Role.ASSISTANT).exists()


def test_only_failed_runs_can_be_retried(conversation):
    _message, run = _send(conversation)
    with pytest.raises(services.RetryNotAllowedError):
        services.retry_run(run)


def test_retry_is_refused_while_another_reply_is_pending(conversation):
    _message, run = _send(conversation, content="[mock-fail]")
    services.execute(run.pk)
    # A reply to another message is still on its way.
    Run.objects.create(conversation=conversation, triggering_message=run.triggering_message, idempotency_key="o:1")
    Run.objects.filter(idempotency_key="o:1").update(attempt=0)
    with pytest.raises(services.ConversationBusyError):
        services.retry_run(Run.objects.get(pk=run.pk))


def test_sweep_fails_stuck_runs_and_requeues_lost_ones(conversation, settings):
    settings.CHAT_RUN_TIMEOUT_SECONDS = 60
    now = timezone.now()
    _message, stuck = _send(conversation, key="a")
    Run.objects.filter(pk=stuck.pk).update(status=Run.Status.RUNNING, started_at=now - timedelta(minutes=5))
    other = ConversationFactory(user=conversation.user)
    _message, lost = _send(other, key="b")
    Run.objects.filter(pk=lost.pk).update(created_at=now - timedelta(minutes=2))
    third = ConversationFactory(user=conversation.user)
    _message, ancient = _send(third, key="c")
    Run.objects.filter(pk=ancient.pk).update(created_at=now - timedelta(minutes=10))
    with mock.patch("baibu.chat.tasks.execute_run.delay") as delay:
        stats = services.sweep_runs(now=now)
    assert stats == {"failed": 2, "requeued": 1}
    delay.assert_called_once_with(str(lost.pk))
    assert Run.objects.get(pk=stuck.pk).error["code"] == "timeout"
    assert Run.objects.get(pk=ancient.pk).error["code"] == "not_started"


def test_reply_arriving_after_timeout_is_dropped(conversation):
    _message, run = _send(conversation)
    run = services.claim(run.pk)
    services.fail(Run.objects.get(pk=run.pk), code="timeout", message="late")
    result = services.complete(run, llm.Completion(content="late reply", model="m"))
    assert result.status == Run.Status.FAILED
    assert not Message.objects.filter(role=Message.Role.ASSISTANT).exists()
    # Failing again keeps the first outcome.
    assert services.fail(run, code="other", message="x").error["code"] == "timeout"


def test_prompt_versions_number_themselves_and_cannot_change(admin_user):
    first = Prompt.objects.create(name="system", body="One")
    second = Prompt.objects.create(name="system", body="Two")
    other = Prompt.objects.create(name="other", body="X")
    assert (first.version, second.version, other.version) == (1, 2, 1)
    first.notes = "fine to annotate"
    first.save()
    first.body = "Changed"
    with pytest.raises(ImmutableRecordError):
        first.save()


def test_events_are_append_only(conversation):
    event = conversation.events.get()
    event.type = "changed"
    with pytest.raises(ImmutableRecordError):
        event.save()
    assert str(event).startswith("changed (")


def test_tasks(conversation):
    from baibu.chat import tasks

    _message, run = _send(conversation)
    assert tasks.execute_run(str(run.pk)) == Run.Status.COMPLETED
    assert tasks.execute_run(str(run.pk)) == "skipped"
    assert tasks.sweep_runs() == {"failed": 0, "requeued": 0}


def test_model_strings(conversation):
    _message, run = _send(conversation)
    conversation.refresh_from_db()
    assert str(conversation) == "Hello there"
    assert "queued" in str(run)
    assert "user message" in str(run.triggering_message)
    assert str(ModelVariant(name="v")) == "v"
    assert conversation.active_run == run
    assert ConversationEvent.objects.count() == 3
