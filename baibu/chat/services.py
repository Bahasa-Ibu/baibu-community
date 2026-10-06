"""Conversations, sends, runs and the audit trail.

A send creates the user's message and a queued Run in one transaction; the
Run is executed by a Celery task once committed. Sends are idempotent: the
same key returns the same message and run. A conversation has at most one
active run at a time. A failed run can be retried, which creates a new run
for the same message, up to ``CHAT_MAX_ATTEMPTS`` per message.

A voice send stores the recording, creates the user's message empty and
queues transcription; the transcript then becomes the message and the reply
is queued as for a typed message. While transcription is pending the
conversation is busy, as it is while a reply is being written.
"""

import json
import logging
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.template import Context
from django.template import Template
from django.template.loader import get_template
from django.utils import timezone
from django.utils.translation import get_language_info

from baibu.core import storage
from baibu.users.consent import consent_state

from . import llm
from . import speech
from . import tools
from .models import AudioClip
from .models import Conversation
from .models import ConversationEvent
from .models import Message
from .models import ModelVariant
from .models import Prompt
from .models import Run
from .models import ToolInvocation

logger = logging.getLogger(__name__)


class ChatError(Exception):
    """A request the user can correct; the message is safe to show."""


class ConversationBusyError(ChatError):
    pass


class RetryNotAllowedError(ChatError):
    pass


BUSY_MESSAGE = "Please wait for the reply to your last message."
AUDIO_AREA = "chat/audio"


def record_event(*, conversation, type: str, run=None, message=None, **payload) -> ConversationEvent:  # noqa: A002
    return ConversationEvent.objects.create(
        conversation=conversation, run=run, message=message, type=type, payload=payload
    )


def start_conversation(*, user, language_code: str = "") -> Conversation:
    tier = consent_state(user=user, scope=settings.CHAT_CONSENT_SCOPE).tier
    conversation = Conversation.objects.create(user=user, language_code=language_code, consent_tier=tier)
    record_event(conversation=conversation, type="conversation_started", consent_tier=tier)
    return conversation


def _enqueue(run: Run) -> None:
    from .tasks import execute_run

    transaction.on_commit(lambda: execute_run.delay(str(run.pk)))


def is_busy(conversation: Conversation) -> bool:
    """A reply is being written, or a voice message is being transcribed."""
    return (
        conversation.runs.filter(status__in=Run.ACTIVE_STATUSES).exists()
        or conversation.audio_clips.filter(status__in=AudioClip.ACTIVE_STATUSES).exists()
    )


def _queue_reply(conversation: Conversation, message: Message, *, via: str = "text") -> Run:
    """Queue the first run for a user message whose content is final. Call
    inside a transaction holding the conversation's row lock."""
    run = Run.objects.create(
        conversation=conversation, triggering_message=message, idempotency_key=f"{message.idempotency_key}:1"
    )
    record_event(
        conversation=conversation, type="message_sent", message=message, characters=len(message.content), via=via
    )
    record_event(conversation=conversation, type="run_queued", run=run, message=message, attempt=1)
    if not conversation.title:
        conversation.title = message.content.splitlines()[0][:80]
    conversation.last_activity_at = timezone.now()
    conversation.save(update_fields=["title", "last_activity_at"])
    _enqueue(run)
    return run


def send_message(*, conversation: Conversation, content: str, idempotency_key: str) -> tuple[Message, Run]:
    """Add the user's message and queue a reply. Safe to call twice with one key."""
    content = content.strip()
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        existing = conversation.messages.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing, existing.runs.order_by("-created_at").first()
        if is_busy(conversation):
            raise ConversationBusyError(BUSY_MESSAGE)
        message = Message.objects.create(
            conversation=conversation, role=Message.Role.USER, content=content, idempotency_key=idempotency_key
        )
        run = _queue_reply(conversation, message)
    return message, run


def retry_run(run: Run) -> Run:
    """Queue a new attempt at a failed run's reply."""
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=run.conversation_id)
        run = Run.objects.get(pk=run.pk)
        if run.status != Run.Status.FAILED:
            msg = "Only a failed reply can be retried."
            raise RetryNotAllowedError(msg)
        latest = run.triggering_message.runs.order_by("-attempt").first()
        if latest.pk != run.pk:
            return latest
        if run.attempt >= settings.CHAT_MAX_ATTEMPTS:
            msg = "This message has been tried too many times."
            raise RetryNotAllowedError(msg)
        if is_busy(conversation):
            raise ConversationBusyError(BUSY_MESSAGE)
        attempt = run.attempt + 1
        new_run = Run.objects.create(
            conversation=conversation,
            triggering_message=run.triggering_message,
            attempt=attempt,
            idempotency_key=f"{run.idempotency_key.rsplit(':', 1)[0]}:{attempt}",
        )
        record_event(
            conversation=conversation, type="run_retried", run=new_run, retried_run=str(run.pk), attempt=attempt
        )
        conversation.last_activity_at = timezone.now()
        conversation.save(update_fields=["last_activity_at"])
        _enqueue(new_run)
    return new_run


# --- Prompt and model -------------------------------------------------------


def active_prompt(name: str = "system") -> Prompt | None:
    return Prompt.objects.filter(name=name, active=True).first()


def render_system_prompt(conversation: Conversation, prompt: Prompt | None) -> str:
    from baibu.core.context_processors import platform

    language_code = conversation.language_code or settings.LANGUAGE_CODE
    try:
        language_name = get_language_info(language_code)["name"]
    except KeyError:
        language_name = language_code
    context = {
        **platform(None),
        "user_name": conversation.user.name,
        "language_code": language_code,
        "language_name": language_name,
    }
    if prompt is None:
        return get_template("chat/system_prompt.txt").render(context).strip()
    return Template(prompt.body).render(Context(context, autoescape=False)).strip()


def default_variant() -> ModelVariant | None:
    return ModelVariant.objects.filter(is_default=True).first()


def build_messages(run: Run, system_prompt: str) -> list[dict]:
    """System prompt, then recent turns up to and including the triggering message."""
    history = list(
        run.conversation.messages.filter(created_at__lte=run.triggering_message.created_at)
        # Voice messages without a transcript have no content to send.
        .exclude(audio__status__in=[*AudioClip.ACTIVE_STATUSES, AudioClip.Status.FAILED])
        .order_by("-created_at", "-id")
        .values("role", "content")[: settings.CHAT_CONTEXT_MESSAGES]
    )
    history.reverse()
    return [{"role": "system", "content": system_prompt}, *history]


# --- Execution --------------------------------------------------------------


def claim(run_id) -> Run | None:
    """Move a queued run to running. Returns None if someone else has it."""
    now = timezone.now()
    claimed = Run.objects.filter(pk=run_id, status=Run.Status.QUEUED).update(status=Run.Status.RUNNING, started_at=now)
    if not claimed:
        return None
    run = Run.objects.select_related("conversation__user", "triggering_message").get(pk=run_id)
    record_event(conversation=run.conversation, type="run_started", run=run)
    return run


def execute(run_id) -> Run | None:
    run = claim(run_id)
    if run is None:
        return None
    prompt = active_prompt()
    variant = default_variant()
    config = llm.ModelConfig.from_variant(variant)
    run.prompt = prompt
    run.model_variant = variant
    run.prompt_version = str(prompt) if prompt else "built-in"
    try:
        messages = build_messages(run, render_system_prompt(run.conversation, prompt))
        completion = generate(run, config, messages)
    except llm.ModelError as exc:
        return fail(run, code=exc.code, message=str(exc))
    except Exception as exc:
        logger.exception("Chat run %s failed", run.pk)
        return fail(run, code="internal_error", message=type(exc).__name__)
    return complete(run, completion)


def generate(run: Run, config: llm.ModelConfig, messages: list[dict]) -> llm.Completion:
    """Ask the model for the reply, running any tools it calls.

    The model may call tools for up to ``CHAT_MAX_TOOL_ROUNDS`` rounds; the
    last call offers no tools, so it has to answer. Sources from tools are
    collected on ``run.sources`` for the reply.
    """
    run.model_name = config.model
    run.sources = []
    available = {tool.name: tool for tool in tools.available_tools()}
    messages = list(messages)
    for round_number in range(settings.CHAT_MAX_TOOL_ROUNDS + 1):
        offer = [tool.schema() for tool in available.values()] if round_number < settings.CHAT_MAX_TOOL_ROUNDS else []
        completion = llm.complete(config, messages, tools=offer or None)
        if not completion.tool_calls:
            return completion
        messages.append(completion.raw_message)
        for call in completion.tool_calls:
            messages.append({"role": "tool", "tool_call_id": call.id, "content": _run_tool(run, available, call)})
    return completion  # pragma: no cover - the last round offers no tools


def _run_tool(run: Run, available: dict, call: llm.ToolCall) -> str:
    started = time.monotonic()
    tool = available.get(call.name)
    invocation = ToolInvocation(run=run, tool_name=call.name[:64], call_id=call.id[:255], arguments=call.arguments)
    try:
        if tool is None:
            msg = f"Unknown tool {call.name!r}."
            raise tools.ToolError(msg)
        result = tool.run(call.arguments)
    except tools.ToolError as exc:
        invocation.status = ToolInvocation.Status.FAILED
        invocation.error = str(exc)[:500]
        content = json.dumps({"error": invocation.error})
    else:
        invocation.status = ToolInvocation.Status.COMPLETED
        invocation.provider = result.provider
        invocation.result_count = len(result.sources)
        run.sources.extend(s for s in result.sources if s not in run.sources)
        content = result.content
    invocation.latency_ms = int((time.monotonic() - started) * 1000)
    invocation.save()
    record_event(
        conversation=run.conversation,
        type=f"tool_{invocation.status}",
        run=run,
        tool=invocation.tool_name,
        invocation=str(invocation.pk),
    )
    return content


def complete(run: Run, completion: llm.Completion) -> Run:
    content = completion.content.strip()
    if not content:
        return fail(run, code="empty_response", message="The model returned an empty reply.")
    with transaction.atomic():
        locked = Run.objects.select_for_update().get(pk=run.pk)
        if locked.status != Run.Status.RUNNING:
            # Timed out and failed by the sweeper meanwhile; keep that outcome.
            return locked
        reply = Message.objects.create(
            conversation=run.conversation,
            role=Message.Role.ASSISTANT,
            content=content,
            run=run,
            sources=getattr(run, "sources", [])[: settings.CHAT_SEARCH_MAX_RESULTS * settings.CHAT_MAX_TOOL_ROUNDS],
        )
        run.status = Run.Status.COMPLETED
        run.model_name = completion.model or run.model_name
        run.usage = completion.usage
        run.latency_ms = completion.latency_ms
        run.completed_at = timezone.now()
        run.save()
        record_event(
            conversation=run.conversation,
            type="run_completed",
            run=run,
            message=reply,
            model=run.model_name,
            prompt=run.prompt_version,
            latency_ms=completion.latency_ms,
        )
        Conversation.objects.filter(pk=run.conversation_id).update(last_activity_at=timezone.now())
    return run


def fail(run: Run, *, code: str, message: str) -> Run:
    with transaction.atomic():
        locked = Run.objects.select_for_update().get(pk=run.pk)
        if locked.status in (Run.Status.COMPLETED, Run.Status.FAILED):
            return locked
        run.status = Run.Status.FAILED
        run.error = {"code": code, "message": message[:500]}
        run.completed_at = timezone.now()
        run.save()
        record_event(conversation=run.conversation, type="run_failed", run=run, code=code)
    logger.warning("Chat run %s failed: %s", run.pk, code)
    return run


def sweep_runs(now=None) -> dict:
    """Fail runs stuck too long and re-send queued runs whose task was lost."""
    now = now or timezone.now()
    timeout = timedelta(seconds=settings.CHAT_RUN_TIMEOUT_SECONDS)
    stats = {"failed": 0, "requeued": 0}
    stuck = Run.objects.filter(status=Run.Status.RUNNING, started_at__lt=now - timeout).select_related("conversation")
    for run in stuck:
        if fail(run, code="timeout", message="No reply in time.").error.get("code") == "timeout":
            stats["failed"] += 1
    lost = Run.objects.filter(status=Run.Status.QUEUED, created_at__lt=now - timeout).select_related("conversation")
    for run in lost:
        if run.created_at < now - 3 * timeout:
            fail(run, code="not_started", message="The reply was never started.")
            stats["failed"] += 1
        else:
            from .tasks import execute_run

            execute_run.delay(str(run.pk))
            stats["requeued"] += 1
    return stats


# --- Voice messages ---------------------------------------------------------


def _enqueue_transcription(clip: AudioClip) -> None:
    from .tasks import transcribe_audio

    transaction.on_commit(lambda: transcribe_audio.delay(str(clip.pk)))


def send_voice(*, conversation: Conversation, audio: bytes, content_type: str, idempotency_key: str) -> Message:
    """Store a recording, add an empty user message and queue transcription.

    Safe to call twice with one key. Storage errors are let through and
    nothing is recorded then.
    """
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        existing = conversation.messages.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
        if is_busy(conversation):
            raise ConversationBusyError(BUSY_MESSAGE)
        clip_id = uuid.uuid7()
        key = storage.save_bytes(
            storage.build_key(AUDIO_AREA, f"{clip_id}.{speech.extension_for(content_type)}"), audio
        )
        try:
            with transaction.atomic():
                message = Message.objects.create(
                    conversation=conversation, role=Message.Role.USER, content="", idempotency_key=idempotency_key
                )
                clip = AudioClip.objects.create(
                    id=clip_id,
                    conversation=conversation,
                    message=message,
                    storage_key=key,
                    content_type=content_type,
                    size_bytes=len(audio),
                )
                record_event(
                    conversation=conversation,
                    type="audio_received",
                    message=message,
                    clip=str(clip.pk),
                    content_type=content_type,
                    bytes=len(audio),
                )
                conversation.last_activity_at = timezone.now()
                conversation.save(update_fields=["last_activity_at"])
        except Exception:
            storage.delete(key)
            raise
        _enqueue_transcription(clip)
    return message


def retry_transcription(clip: AudioClip) -> AudioClip:
    """Queue another attempt at a failed transcription."""
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=clip.conversation_id)
        clip = AudioClip.objects.get(pk=clip.pk)
        if clip.status != AudioClip.Status.FAILED:
            msg = "Only a failed transcription can be retried."
            raise RetryNotAllowedError(msg)
        if clip.attempt >= settings.CHAT_MAX_ATTEMPTS:
            msg = "This message has been tried too many times."
            raise RetryNotAllowedError(msg)
        if is_busy(conversation):
            raise ConversationBusyError(BUSY_MESSAGE)
        clip.status = AudioClip.Status.PENDING
        clip.attempt += 1
        clip.error = {}
        clip.queued_at = timezone.now()
        clip.started_at = clip.completed_at = None
        clip.save()
        record_event(
            conversation=conversation,
            type="transcription_retried",
            message=clip.message,
            clip=str(clip.pk),
            attempt=clip.attempt,
        )
        conversation.last_activity_at = timezone.now()
        conversation.save(update_fields=["last_activity_at"])
        _enqueue_transcription(clip)
    return clip


def transcribe(clip_id) -> AudioClip | None:
    """Transcribe a pending clip; on success queue the reply."""
    claimed = AudioClip.objects.filter(pk=clip_id, status=AudioClip.Status.PENDING).update(
        status=AudioClip.Status.TRANSCRIBING, started_at=timezone.now()
    )
    if not claimed:
        return None
    clip = AudioClip.objects.select_related("conversation", "message").get(pk=clip_id)
    provider = speech.get_provider()
    try:
        if provider is None:
            msg = "Voice input is not configured."
            raise speech.TranscriptionError(msg, code="not_configured")
        audio = storage.read_bytes(clip.storage_key)
        if audio is None:
            msg = "The recording is missing from storage."
            raise speech.TranscriptionError(msg, code="missing_audio")
        transcript = provider.transcribe(
            audio, content_type=clip.content_type, language_code=clip.conversation.language_code
        )
    except speech.TranscriptionError as exc:
        return fail_transcription(clip, code=exc.code, message=str(exc))
    except Exception as exc:
        logger.exception("Transcription of %s failed", clip.pk)
        return fail_transcription(clip, code="internal_error", message=type(exc).__name__)
    text = " ".join(transcript.text.split())[: settings.CHAT_MAX_MESSAGE_CHARACTERS]
    if not text:
        return fail_transcription(clip, code="no_speech", message="No speech was recognised.")
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=clip.conversation_id)
        locked = AudioClip.objects.select_for_update().get(pk=clip.pk)
        if locked.status != AudioClip.Status.TRANSCRIBING:
            # Timed out and failed by the sweeper meanwhile; keep that outcome.
            return locked
        clip.status = AudioClip.Status.TRANSCRIBED
        clip.provider = (transcript.provider or getattr(provider, "name", ""))[:128]
        clip.language = transcript.language[:24]
        clip.duration_seconds = transcript.duration
        clip.completed_at = timezone.now()
        clip.save()
        message = clip.message
        message.content = text
        message.save(update_fields=["content"])
        record_event(
            conversation=conversation,
            type="transcription_completed",
            message=message,
            clip=str(clip.pk),
            provider=clip.provider,
            characters=len(text),
            duration_seconds=clip.duration_seconds,
        )
        _queue_reply(conversation, message, via="voice")
    return clip


def fail_transcription(clip: AudioClip, *, code: str, message: str) -> AudioClip:
    with transaction.atomic():
        locked = AudioClip.objects.select_for_update().get(pk=clip.pk)
        if locked.status in (AudioClip.Status.TRANSCRIBED, AudioClip.Status.FAILED):
            return locked
        clip.status = AudioClip.Status.FAILED
        clip.error = {"code": code, "message": message[:500]}
        clip.completed_at = timezone.now()
        clip.save()
        record_event(
            conversation=clip.conversation,
            type="transcription_failed",
            message=clip.message,
            clip=str(clip.pk),
            code=code,
        )
    logger.warning("Transcription of %s failed: %s", clip.pk, code)
    return clip


def sweep_transcriptions(now=None) -> dict:
    """Fail transcriptions stuck too long and re-send pending ones whose task was lost."""
    now = now or timezone.now()
    timeout = timedelta(seconds=settings.CHAT_RUN_TIMEOUT_SECONDS)
    stats = {"failed": 0, "requeued": 0}
    stuck = AudioClip.objects.filter(status=AudioClip.Status.TRANSCRIBING, started_at__lt=now - timeout)
    for clip in stuck.select_related("conversation"):
        if fail_transcription(clip, code="timeout", message="No transcript in time.").error.get("code") == "timeout":
            stats["failed"] += 1
    lost = AudioClip.objects.filter(status=AudioClip.Status.PENDING, queued_at__lt=now - timeout)
    for clip in lost.select_related("conversation"):
        if clip.queued_at < now - 3 * timeout:
            fail_transcription(clip, code="not_started", message="The transcription was never started.")
            stats["failed"] += 1
        else:
            from .tasks import transcribe_audio

            transcribe_audio.delay(str(clip.pk))
            stats["requeued"] += 1
    return stats


def new_idempotency_key() -> str:
    return uuid.uuid4().hex


# --- Reports ----------------------------------------------------------------


def report_message(*, message: Message, user, reason: str, note: str = ""):
    """Flag an assistant reply for staff. Reporting the same reply twice is a no-op."""
    from .models import ChatFlag

    if message.role != Message.Role.ASSISTANT or message.conversation.user_id != user.pk:
        msg = "Only replies in your own conversations can be reported."
        raise ChatError(msg)
    flag, created = ChatFlag.objects.get_or_create(
        message=message,
        reported_by=user,
        defaults={"conversation": message.conversation, "reason": reason, "note": note.strip()[:500]},
    )
    if created:
        record_event(conversation=message.conversation, type="reply_reported", message=message, reason=reason)
    return flag


def decide_flag(flag, status: str, *, reviewer, note: str = "") -> bool:
    """Record the one staff decision on a report. Returns False if already decided."""
    from django.urls import reverse

    from baibu.notifications.services import notify

    from .models import ChatFlag

    if status not in {ChatFlag.Status.CONFIRMED, ChatFlag.Status.DISMISSED}:
        msg = f"Not a decision: {status}"
        raise ValueError(msg)
    with transaction.atomic():
        locked = ChatFlag.objects.select_for_update().get(pk=flag.pk)
        if locked.status != ChatFlag.Status.OPEN:
            return False
        locked.status = status
        locked.decided_by = reviewer
        locked.decided_at = timezone.now()
        locked.decision_note = note.strip()
        locked.save()
        record_event(conversation=locked.conversation, type=f"report_{status}", message=locked.message)
    notify(
        locked.reported_by,
        kind="chat_report_reviewed",
        link=reverse("chat:conversation", args=[locked.conversation_id]),
    )
    flag.refresh_from_db()
    return True
