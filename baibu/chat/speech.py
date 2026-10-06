"""Speech to text for voice messages.

Voice input is off unless ``CHAT_STT_PROVIDER`` names a subclass of
:class:`SpeechToText`. Two are included:

- :class:`LiteLLMSpeechToText` sends the audio to any transcription model
  LiteLLM supports, including a self-hosted server that speaks the
  OpenAI-compatible transcription API. The deployment chooses the model.
- :class:`MockSpeechToText` returns made-up transcripts without any model,
  for development and tests.

A provider returns a :class:`Transcript` or raises :class:`TranscriptionError`.
"""

import os
from dataclasses import dataclass
from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string


class TranscriptionError(Exception):
    """Transcription failed. ``code`` is safe to show and store."""

    def __init__(self, message: str, *, code: str = "transcription_error"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Transcript:
    text: str
    # Language the provider detected or was told, if it says.
    language: str = ""
    # Length of the audio in seconds, if the provider says.
    duration: float | None = None
    # Which provider and model produced the text, for the record.
    provider: str = ""


class SpeechToText:
    name = "provider"

    def transcribe(self, audio: bytes, *, content_type: str, language_code: str = "") -> Transcript:
        raise NotImplementedError


class MockSpeechToText(SpeechToText):
    """Deterministic transcripts for development and tests.

    - Audio containing ``[stt-fail]`` fails.
    - Audio containing ``[stt-empty]`` gives an empty transcript.
    - Audio containing ``[say:some text]`` is transcribed as ``some text``.
    - Anything else is transcribed as :attr:`default_text`.
    """

    name = "mock"
    default_text = "This is a mock transcript."

    def transcribe(self, audio: bytes, *, content_type: str, language_code: str = "") -> Transcript:
        if b"[stt-fail]" in audio:
            msg = "Mock transcription failure."
            raise TranscriptionError(msg, code="mock_failure")
        text = self.default_text
        if b"[stt-empty]" in audio:
            text = ""
        elif (start := audio.find(b"[say:")) >= 0 and (end := audio.find(b"]", start)) > start:
            text = audio[start + 5 : end].decode("utf-8", errors="replace")
        return Transcript(text=text, language=language_code, duration=round(len(audio) / 1000, 3), provider="mock")


# File name extensions for the content types browsers record in. Some
# transcription servers look at the name to decide how to decode the audio.
EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/flac": "flac",
}


def extension_for(content_type: str) -> str:
    return EXTENSIONS.get(content_type, "bin")


class LiteLLMSpeechToText(SpeechToText):
    """Transcribes through ``litellm.transcription``.

    Settings: ``CHAT_STT_MODEL`` (any transcription model name LiteLLM
    accepts), ``CHAT_STT_API_BASE``, ``CHAT_STT_API_KEY_ENV`` (the *name* of
    the environment variable holding the key), ``CHAT_STT_TIMEOUT`` and
    ``CHAT_STT_PARAMETERS`` (extra arguments for every call, for example
    ``{"language": "sw"}``).
    """

    name = "litellm"

    def transcribe(self, audio: bytes, *, content_type: str, language_code: str = "") -> Transcript:
        import litellm

        model = settings.CHAT_STT_MODEL
        if not model:
            msg = "CHAT_STT_MODEL is not set."
            raise TranscriptionError(msg, code="not_configured")
        kwargs = {
            **settings.CHAT_STT_PARAMETERS,
            "model": model,
            "file": (f"audio.{extension_for(content_type)}", audio, content_type),
            "timeout": settings.CHAT_STT_TIMEOUT,
        }
        if settings.CHAT_STT_API_BASE:
            kwargs["api_base"] = settings.CHAT_STT_API_BASE
        if settings.CHAT_STT_API_KEY_ENV and (key := os.environ.get(settings.CHAT_STT_API_KEY_ENV, "")):
            kwargs["api_key"] = key
        try:
            response = litellm.transcription(**kwargs)
        except Exception as exc:
            code = "timeout" if "timeout" in type(exc).__name__.lower() else "transcription_error"
            msg = f"Transcription failed: {type(exc).__name__}"
            raise TranscriptionError(msg, code=code) from exc
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            msg = "Transcription returned no text."
            raise TranscriptionError(msg, code="empty_response")
        duration = getattr(response, "duration", None)
        language = getattr(response, "language", None)
        return Transcript(
            text=text,
            language=language if isinstance(language, str) else "",
            duration=float(duration) if isinstance(duration, int | float) else None,
            provider=f"{self.name}:{model}"[:128],
        )


@cache
def _provider_class(path: str) -> type[SpeechToText]:
    return import_string(path)


def voice_enabled() -> bool:
    return bool(settings.CHAT_STT_PROVIDER)


def get_provider() -> SpeechToText | None:
    path = settings.CHAT_STT_PROVIDER
    return _provider_class(path)() if path else None
