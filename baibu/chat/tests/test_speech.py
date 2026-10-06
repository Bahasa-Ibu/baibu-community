from types import SimpleNamespace
from unittest import mock

import pytest

from baibu.chat import speech


def test_mock_transcribes_marker_default_and_fails_on_purpose():
    stt = speech.MockSpeechToText()
    said = stt.transcribe(b"RIFF....[say:Habari za asubuhi]....", content_type="audio/wav", language_code="sw")
    assert said.text == "Habari za asubuhi"
    assert said.language == "sw"
    assert said.provider == "mock"
    assert said.duration == pytest.approx(0.035)
    assert stt.transcribe(b"OggS", content_type="audio/ogg").text == speech.MockSpeechToText.default_text
    assert stt.transcribe(b"OggS [stt-empty]", content_type="audio/ogg").text == ""
    with pytest.raises(speech.TranscriptionError) as excinfo:
        stt.transcribe(b"OggS [stt-fail]", content_type="audio/ogg")
    assert excinfo.value.code == "mock_failure"


def test_base_provider_must_be_subclassed():
    with pytest.raises(NotImplementedError):
        speech.SpeechToText().transcribe(b"x", content_type="audio/webm")


def test_provider_comes_from_settings(settings):
    settings.CHAT_STT_PROVIDER = ""
    assert speech.get_provider() is None
    assert not speech.voice_enabled()
    settings.CHAT_STT_PROVIDER = "baibu.chat.speech.MockSpeechToText"
    assert isinstance(speech.get_provider(), speech.MockSpeechToText)
    assert speech.voice_enabled()


def test_extensions():
    assert speech.extension_for("audio/webm") == "webm"
    assert speech.extension_for("audio/mp4") == "m4a"
    assert speech.extension_for("audio/unknown") == "bin"


@pytest.fixture
def stt_settings(settings, monkeypatch):
    settings.CHAT_STT_MODEL = "example/transcriber-1"
    settings.CHAT_STT_API_BASE = "http://stt.example.org/v1"
    settings.CHAT_STT_API_KEY_ENV = "EXAMPLE_STT_KEY"
    settings.CHAT_STT_TIMEOUT = 30
    settings.CHAT_STT_PARAMETERS = {"language": "sw"}
    monkeypatch.setenv("EXAMPLE_STT_KEY", "secret-from-env")
    return settings


def test_litellm_provider_sends_audio_and_reads_transcript(stt_settings):
    response = SimpleNamespace(text="Jambo", language="swahili", duration=2.5)
    with mock.patch("litellm.transcription", return_value=response) as transcription:
        result = speech.LiteLLMSpeechToText().transcribe(b"OggS-audio", content_type="audio/ogg", language_code="en")
    assert result == speech.Transcript(
        text="Jambo", language="swahili", duration=2.5, provider="litellm:example/transcriber-1"
    )
    kwargs = transcription.call_args.kwargs
    assert kwargs["model"] == "example/transcriber-1"
    assert kwargs["file"] == ("audio.ogg", b"OggS-audio", "audio/ogg")
    assert kwargs["api_base"] == "http://stt.example.org/v1"
    assert kwargs["api_key"] == "secret-from-env"
    assert kwargs["timeout"] == 30
    assert kwargs["language"] == "sw"


def test_litellm_provider_without_endpoint_key_or_extras(stt_settings, monkeypatch):
    stt_settings.CHAT_STT_API_BASE = ""
    stt_settings.CHAT_STT_PARAMETERS = {}
    monkeypatch.delenv("EXAMPLE_STT_KEY")
    with mock.patch("litellm.transcription", return_value=SimpleNamespace(text="Jambo")) as transcription:
        result = speech.LiteLLMSpeechToText().transcribe(b"x", content_type="audio/webm")
    assert (result.language, result.duration) == ("", None)
    assert "api_base" not in transcription.call_args.kwargs
    assert "api_key" not in transcription.call_args.kwargs


def test_litellm_provider_errors(stt_settings):
    stt = speech.LiteLLMSpeechToText()

    class FakeTimeoutError(Exception):
        pass

    with (
        mock.patch("litellm.transcription", side_effect=FakeTimeoutError("slow")),
        pytest.raises(speech.TranscriptionError) as excinfo,
    ):
        stt.transcribe(b"x", content_type="audio/webm")
    assert excinfo.value.code == "timeout"
    with (
        mock.patch("litellm.transcription", side_effect=RuntimeError("down")),
        pytest.raises(speech.TranscriptionError) as excinfo,
    ):
        stt.transcribe(b"x", content_type="audio/webm")
    assert excinfo.value.code == "transcription_error"
    assert "down" not in str(excinfo.value)
    with (
        mock.patch("litellm.transcription", return_value=SimpleNamespace(text=None)),
        pytest.raises(speech.TranscriptionError) as excinfo,
    ):
        stt.transcribe(b"x", content_type="audio/webm")
    assert excinfo.value.code == "empty_response"
    stt_settings.CHAT_STT_MODEL = ""
    with pytest.raises(speech.TranscriptionError) as excinfo:
        stt.transcribe(b"x", content_type="audio/webm")
    assert excinfo.value.code == "not_configured"
