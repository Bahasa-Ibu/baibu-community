"""Voice messages. The audio is a few synthetic bytes with a fake header; the
mock speech-to-text provider reads markers such as ``[say:...]`` from it."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from baibu.chat import services
from baibu.chat.models import AudioClip
from baibu.chat.models import Conversation
from baibu.chat.models import Message
from baibu.chat.models import Run
from baibu.core import storage
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory

from .factories import ConversationFactory

pytestmark = pytest.mark.django_db

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}
AUDIO = b"\x1aE\xdf\xa3 fake webm [say:When is the next market day?]"


@pytest.fixture(autouse=True)
def _voice_on(settings):
    settings.CHAT_STT_PROVIDER = "baibu.chat.speech.MockSpeechToText"


@pytest.fixture
def chatter(client, user):
    record_consent(user=user, tier=ConsentRecord.Tier.EVAL_ONLY, source="test", scope="chat")
    client.force_login(user)
    return user


@pytest.fixture
def conversation(chatter):
    return services.start_conversation(user=chatter, language_code="en")


def _voice(conversation, audio=AUDIO, key="v1", content_type="audio/webm"):
    return services.send_voice(conversation=conversation, audio=audio, content_type=content_type, idempotency_key=key)


def _upload(client, conversation, audio=AUDIO, content_type="audio/webm;codecs=opus", key="v1", **extra):
    url = reverse("chat:voice", args=[conversation.pk]) if conversation else reverse("chat:voice_new")
    upload = SimpleUploadedFile("voice.webm", audio, content_type=content_type)
    return client.post(url, {"audio": upload, "idempotency_key": key}, **extra)


def _events(conversation):
    return list(conversation.events.values_list("type", flat=True))


# --- Services ---------------------------------------------------------------


def test_voice_send_stores_audio_and_queues_transcription(conversation, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        message = _voice(conversation)
    clip = message.audio
    assert message.content == ""
    assert clip.status == AudioClip.Status.PENDING
    assert clip.storage_key == f"chat/audio/{timezone.now():%Y/%m/%d}/{clip.pk}.webm"
    assert storage.read_bytes(clip.storage_key) == AUDIO
    assert (clip.content_type, clip.size_bytes) == ("audio/webm", len(AUDIO))
    assert not Run.objects.exists()
    assert _events(conversation) == ["conversation_started", "audio_received"]
    assert len(callbacks) == 1
    # The same key again is the same message; no second recording is stored.
    assert _voice(conversation).pk == message.pk
    assert AudioClip.objects.count() == 1


def test_transcript_becomes_the_message_and_reply_is_queued(conversation, django_capture_on_commit_callbacks):
    message = _voice(conversation)
    with (
        mock.patch("baibu.chat.tasks.execute_run.delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        clip = services.transcribe(message.audio.pk)
    message.refresh_from_db()
    conversation.refresh_from_db()
    assert clip.status == AudioClip.Status.TRANSCRIBED
    assert (clip.provider, clip.language, clip.duration_seconds) == ("mock", "en", pytest.approx(0.049))
    assert message.content == "When is the next market day?"
    assert conversation.title == "When is the next market day?"
    run = Run.objects.get()
    assert run.triggering_message == message
    assert run.idempotency_key == "v1:1"
    delay.assert_called_once_with(str(run.pk))
    assert _events(conversation) == [
        "conversation_started",
        "audio_received",
        "transcription_completed",
        "message_sent",
        "run_queued",
    ]
    assert conversation.events.get(type="message_sent").payload["via"] == "voice"
    # The reply sees the transcript.
    run = services.execute(run.pk)
    assert run.reply.content == "You said: When is the next market day?"
    # A second transcription of the same clip does nothing.
    assert services.transcribe(clip.pk) is None


def test_conversation_is_busy_while_transcribing(conversation):
    message = _voice(conversation)
    with pytest.raises(services.ConversationBusyError):
        services.send_message(conversation=conversation, content="Typed meanwhile", idempotency_key="t1")
    with pytest.raises(services.ConversationBusyError):
        _voice(conversation, key="v2")
    assert services.is_busy(conversation)
    services.transcribe(message.audio.pk)
    # Now the reply is being written: still busy.
    assert services.is_busy(conversation)
    services.execute(Run.objects.get().pk)
    assert not services.is_busy(conversation)
    services.send_message(conversation=conversation, content="Typed after", idempotency_key="t1")


def test_retry_rules(conversation, settings):
    settings.CHAT_MAX_ATTEMPTS = 2
    message = _voice(conversation, audio=b"OggS [stt-fail]")
    clip = services.transcribe(message.audio.pk)
    assert clip.status == AudioClip.Status.FAILED
    assert clip.error["code"] == "mock_failure"
    assert "transcription_failed" in _events(conversation)
    assert not services.is_busy(conversation)
    retried = services.retry_transcription(clip)
    assert (retried.status, retried.attempt, retried.error) == (AudioClip.Status.PENDING, 2, {})
    assert "transcription_retried" in _events(conversation)
    with pytest.raises(services.RetryNotAllowedError, match="Only a failed"):
        services.retry_transcription(retried)
    clip = services.transcribe(retried.pk)
    assert clip.status == AudioClip.Status.FAILED
    with pytest.raises(services.RetryNotAllowedError, match="too many times"):
        services.retry_transcription(clip)
    # Typing instead works, and the failed voice message is left out of the model's context.
    _message, run = services.send_message(conversation=conversation, content="Typed instead", idempotency_key="t1")
    messages = services.build_messages(run, "system")
    assert [m["content"] for m in messages] == ["system", "Typed instead"]


def test_retry_refused_while_busy(conversation):
    message = _voice(conversation, audio=b"OggS [stt-fail]")
    clip = services.transcribe(message.audio.pk)
    services.send_message(conversation=conversation, content="Typed instead", idempotency_key="t1")
    with pytest.raises(services.ConversationBusyError):
        services.retry_transcription(clip)


@pytest.mark.parametrize(
    ("audio", "code"),
    [(b"OggS [stt-empty]", "no_speech"), (b"OggS", None)],
)
def test_empty_transcript_and_missing_audio(conversation, audio, code):
    message = _voice(conversation, audio=audio)
    if code is None:
        storage.delete(message.audio.storage_key)
        code = "missing_audio"
    clip = services.transcribe(message.audio.pk)
    assert clip.error["code"] == code
    assert not Run.objects.exists()


def test_unexpected_provider_error_and_missing_provider(conversation, settings):
    message = _voice(conversation)
    with mock.patch("baibu.chat.speech.MockSpeechToText.transcribe", side_effect=ValueError("boom")):
        clip = services.transcribe(message.audio.pk)
    assert clip.error == {"code": "internal_error", "message": "ValueError"}
    other = ConversationFactory(user=conversation.user)
    message = _voice(other, key="v2")
    settings.CHAT_STT_PROVIDER = ""
    assert services.transcribe(message.audio.pk).error["code"] == "not_configured"


def test_long_transcript_is_cut_to_the_message_limit(conversation, settings):
    settings.CHAT_MAX_MESSAGE_CHARACTERS = 10
    message = _voice(conversation, audio=b"[say:one two  three four five]")
    services.transcribe(message.audio.pk)
    message.refresh_from_db()
    assert message.content == "one two th"


def test_transcript_arriving_after_timeout_is_dropped(conversation):
    message = _voice(conversation)
    clip = message.audio
    real = services.speech.MockSpeechToText.transcribe

    def slow(self, *args, **kwargs):
        services.fail_transcription(AudioClip.objects.get(pk=clip.pk), code="timeout", message="late")
        return real(self, *args, **kwargs)

    with mock.patch("baibu.chat.speech.MockSpeechToText.transcribe", slow):
        result = services.transcribe(clip.pk)
    assert result.error["code"] == "timeout"
    message.refresh_from_db()
    assert message.content == ""
    assert not Run.objects.exists()
    # Failing again keeps the first outcome.
    assert services.fail_transcription(result, code="other", message="x").error["code"] == "timeout"


def test_storage_failure_records_nothing(conversation):
    with (
        mock.patch("baibu.core.storage.save_bytes", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        _voice(conversation)
    assert not Message.objects.exists()


def test_database_failure_removes_stored_audio(conversation):
    saved = []
    real_save = storage.save_bytes

    def save(key, data):
        saved.append(real_save(key, data))
        return saved[-1]

    with (
        mock.patch("baibu.core.storage.save_bytes", save),
        mock.patch("baibu.chat.models.AudioClip.objects.create", side_effect=RuntimeError("db")),
        pytest.raises(RuntimeError),
    ):
        _voice(conversation)
    assert not Message.objects.exists()
    assert len(saved) == 1
    assert not storage.exists(saved[0])


def test_sweep_fails_stuck_and_requeues_lost_transcriptions(conversation, settings):
    settings.CHAT_RUN_TIMEOUT_SECONDS = 60
    now = timezone.now()
    stuck = _voice(conversation, key="a").audio
    AudioClip.objects.filter(pk=stuck.pk).update(
        status=AudioClip.Status.TRANSCRIBING, started_at=now - timedelta(minutes=5)
    )
    lost = _voice(ConversationFactory(user=conversation.user), key="b").audio
    AudioClip.objects.filter(pk=lost.pk).update(queued_at=now - timedelta(minutes=2))
    ancient = _voice(ConversationFactory(user=conversation.user), key="c").audio
    AudioClip.objects.filter(pk=ancient.pk).update(queued_at=now - timedelta(minutes=10))
    with mock.patch("baibu.chat.tasks.transcribe_audio.delay") as delay:
        stats = services.sweep_transcriptions(now=now)
    assert stats == {"failed": 2, "requeued": 1}
    delay.assert_called_once_with(str(lost.pk))
    assert AudioClip.objects.get(pk=stuck.pk).error["code"] == "timeout"
    assert AudioClip.objects.get(pk=ancient.pk).error["code"] == "not_started"


def test_tasks(conversation):
    from baibu.chat import tasks

    message = _voice(conversation)
    assert tasks.transcribe_audio(str(message.audio.pk)) == AudioClip.Status.TRANSCRIBED
    assert tasks.transcribe_audio(str(message.audio.pk)) == "skipped"
    assert tasks.sweep_transcriptions() == {"failed": 0, "requeued": 0}
    assert "transcribed" in str(AudioClip.objects.get())


def test_task_survives_deletion_during_transcription(conversation):
    from baibu.chat import tasks

    message = _voice(conversation)

    def delete_meanwhile(self, *args, **kwargs):
        Conversation.objects.filter(pk=conversation.pk).delete()
        return services.speech.Transcript(text="Too late")

    with mock.patch("baibu.chat.speech.MockSpeechToText.transcribe", delete_meanwhile):
        assert tasks.transcribe_audio(str(message.audio.pk)) == "deleted"
    assert not Run.objects.exists()


@pytest.mark.parametrize("delete", ["message", "conversation", "user"])
def test_deleting_removes_the_recording(conversation, delete, django_capture_on_commit_callbacks):
    key = _voice(conversation).audio.storage_key
    assert storage.exists(key)
    target = {"message": Message.objects.get(), "conversation": conversation, "user": conversation.user}[delete]
    with django_capture_on_commit_callbacks(execute=True):
        target.delete()
    assert not AudioClip.objects.exists()
    assert not storage.exists(key)


# --- Views ------------------------------------------------------------------


def test_upload_shows_transcribing_then_transcript(client, conversation):
    response = _upload(client, conversation, **FETCH)
    assert response.status_code == 200
    assert response["X-Chat-Pending"] == "1"
    page = response.content.decode()
    assert "Transcribing" in page
    assert "Writing a reply" not in page
    clip = AudioClip.objects.get()
    assert clip.content_type == "audio/webm"
    services.transcribe(clip.pk)
    page = client.get(reverse("chat:messages", args=[conversation.pk]), **FETCH).content.decode()
    assert "Voice message" in page
    assert "When is the next market day?" in page
    assert "Writing a reply" in page
    assert reverse("chat:audio", args=[clip.pk]) in page


def test_upload_without_javascript_redirects(client, conversation):
    response = _upload(client, conversation)
    assert response.url == reverse("chat:conversation", args=[conversation.pk])
    assert AudioClip.objects.count() == 1


@pytest.mark.parametrize(
    ("audio", "content_type", "error"),
    [
        (AUDIO, "text/html", "not supported"),
        (b"", "audio/webm", "empty"),
        (b"x" * 101, "audio/webm", "too long"),
    ],
)
def test_upload_validation(client, conversation, settings, audio, content_type, error):
    settings.CHAT_VOICE_MAX_BYTES = 100
    response = _upload(client, conversation, audio=audio, content_type=content_type, **FETCH)
    assert response.status_code == 400
    assert error in response.content.decode()
    assert not AudioClip.objects.exists()
    plain = _upload(client, conversation, audio=audio, content_type=content_type, follow=True)
    assert error in plain.content.decode()


def test_upload_while_busy_is_refused(client, conversation):
    services.send_message(conversation=conversation, content="Typed", idempotency_key="t1")
    response = _upload(client, conversation, **FETCH)
    assert response.status_code == 400
    assert "wait for the reply" in response.content.decode()
    assert not AudioClip.objects.exists()


def test_upload_is_idempotent(client, conversation):
    _upload(client, conversation, **FETCH)
    again = _upload(client, conversation, **FETCH)
    assert again.status_code == 200
    assert AudioClip.objects.count() == 1


def test_new_conversation_by_voice(client, chatter):
    response = _upload(client, None, **FETCH)
    conversation = Conversation.objects.get()
    assert response.url == reverse("chat:conversation", args=[conversation.pk])
    assert conversation.audio_clips.count() == 1
    # The same recording posted twice opens the same conversation.
    assert _upload(client, None, **FETCH).url == response.url
    assert Conversation.objects.count() == 1


def test_new_conversation_by_voice_validation(client, chatter):
    response = _upload(client, None, content_type="video/mp4", **FETCH)
    assert response.status_code == 400
    assert response["Content-Type"].startswith("text/plain")
    assert "not supported" in response.content.decode()
    plain = _upload(client, None, content_type="video/mp4")
    assert plain.url == reverse("chat:home")
    assert not Conversation.objects.exists()


def test_new_conversation_by_voice_storage_failure_leaves_nothing(client, chatter):
    client.raise_request_exception = False
    with mock.patch("baibu.core.storage.save_bytes", side_effect=OSError("disk full")):
        response = _upload(client, None)
    assert response.status_code == 500
    assert not Conversation.objects.exists()


def test_failed_transcription_offers_retry(client, conversation, settings):
    settings.CHAT_MAX_ATTEMPTS = 2
    _upload(client, conversation, audio=b"OggS [stt-fail]")
    clip = services.transcribe(AudioClip.objects.get().pk)
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert "could not be transcribed" in page
    assert "type your message instead" in page
    retry_url = reverse("chat:voice_retry", args=[clip.pk])
    assert retry_url in page
    response = client.post(retry_url, **FETCH)
    assert response.status_code == 200
    assert response["X-Chat-Pending"] == "1"
    services.transcribe(clip.pk)
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert retry_url not in page
    refused = client.post(retry_url, **FETCH)
    assert refused.status_code == 400
    assert "too many times" in refused.content.decode()
    refused = client.post(retry_url, follow=True)
    assert "too many times" in refused.content.decode()


def test_retry_without_javascript_redirects(client, conversation):
    _upload(client, conversation, audio=b"OggS [stt-fail]")
    clip = services.transcribe(AudioClip.objects.get().pk)
    response = client.post(reverse("chat:voice_retry", args=[clip.pk]))
    assert response.url == reverse("chat:conversation", args=[conversation.pk])


def test_owner_can_play_back_their_recording(client, conversation):
    _upload(client, conversation)
    clip = AudioClip.objects.get()
    response = client.get(reverse("chat:audio", args=[clip.pk]))
    assert response.status_code == 200
    assert response.content == AUDIO
    assert response["Content-Type"] == "audio/webm"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in response["Cache-Control"]
    storage.delete(clip.storage_key)
    assert client.get(reverse("chat:audio", args=[clip.pk])).status_code == 404


def test_recordings_are_private(client, chatter):
    other = ConversationFactory(user=UserFactory())
    message = _voice(other)
    assert client.get(reverse("chat:audio", args=[message.audio.pk])).status_code == 404
    assert client.post(reverse("chat:voice_retry", args=[message.audio.pk])).status_code == 404
    assert _upload(client, other).status_code == 404
    assert AudioClip.objects.count() == 1


def test_composer_offers_recording_only_when_voice_is_on(client, conversation, settings):
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert "data-voice-record" in page
    assert reverse("chat:voice", args=[conversation.pk]) in page
    home = client.get(reverse("chat:home")).content.decode()
    assert reverse("chat:voice_new") in home
    assert "js/chat.js" in home
    settings.CHAT_STT_PROVIDER = ""
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert "data-voice-record" not in page
    home = client.get(reverse("chat:home")).content.decode()
    assert "data-voice-record" not in home
    assert "js/chat.js" not in home


def test_voice_endpoints_404_when_off(client, conversation, settings):
    settings.CHAT_STT_PROVIDER = ""
    message = _voice(conversation)
    assert _upload(client, conversation, key="v2").status_code == 404
    assert _upload(client, None, key="v3").status_code == 404
    assert client.post(reverse("chat:voice_retry", args=[message.audio.pk])).status_code == 404
