"""Sorting provider failures and retrying the ones that clear by themselves."""

from types import SimpleNamespace
from unittest import mock

import pytest

from baibu.chat import llm
from baibu.chat import provider_errors as pe
from baibu.chat import speech


class RateLimitError(Exception):
    pass


class APIConnectionTimeoutError(Exception):
    pass


class ServiceUnavailableError(Exception):
    pass


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (RateLimitError("slow down"), pe.RATE_LIMITED),
        (Exception("HTTP 429 Too Many Requests"), pe.RATE_LIMITED),
        (Exception('{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}'), pe.RATE_LIMITED),
        (type("E", (Exception,), {"status_code": 429})("x"), pe.RATE_LIMITED),
        (APIConnectionTimeoutError("x"), pe.TIMEOUT),
        (Exception("the read timed out"), pe.TIMEOUT),
        (ServiceUnavailableError("x"), pe.TRANSIENT),
        (Exception("Server error: HTTP 503"), pe.TRANSIENT),
        (type("E", (Exception,), {"status_code": 500})("x"), pe.TRANSIENT),
        (Exception("status_code: 403 forbidden"), pe.PERMISSION_DENIED),
        (Exception("code 401"), pe.PERMISSION_DENIED),
        (Exception("status 400 bad request"), pe.BAD_REQUEST),
        (ValueError("anything else"), pe.OTHER),
        (Exception("tokens: 4290 used"), pe.OTHER),
    ],
)
def test_classify(exc, kind):
    assert pe.classify(exc) == kind


@pytest.fixture
def no_sleep():
    with mock.patch("baibu.chat.provider_errors.time.sleep") as sleep:
        yield sleep


def test_retries_rate_limits_until_the_call_works(settings, no_sleep):
    settings.CHAT_PROVIDER_RETRY_SECONDS = 60
    call = mock.Mock(side_effect=[RateLimitError("x"), ServiceUnavailableError("x"), "done"])
    assert pe.call_with_retry(call) == "done"
    assert call.call_count == 3
    waits = [c.args[0] for c in no_sleep.call_args_list]
    assert len(waits) == 2
    assert waits[1] > waits[0] * 1.1  # waits grow


def test_gives_up_when_the_waiting_budget_is_spent(settings, no_sleep):
    settings.CHAT_PROVIDER_RETRY_SECONDS = 5
    call = mock.Mock(side_effect=RateLimitError("x"))
    with pytest.raises(RateLimitError):
        pe.call_with_retry(call)
    assert sum(c.args[0] for c in no_sleep.call_args_list) == pytest.approx(5)
    assert call.call_count > 1


def test_retrying_can_be_turned_off(settings, no_sleep):
    settings.CHAT_PROVIDER_RETRY_SECONDS = 0
    call = mock.Mock(side_effect=RateLimitError("x"))
    with pytest.raises(RateLimitError):
        pe.call_with_retry(call)
    assert call.call_count == 1
    no_sleep.assert_not_called()


@pytest.mark.parametrize("exc", [ValueError("x"), APIConnectionTimeoutError("x"), Exception("status 403")])
def test_other_failures_are_raised_at_once(settings, no_sleep, exc):
    settings.CHAT_PROVIDER_RETRY_SECONDS = 60
    call = mock.Mock(side_effect=exc)
    with pytest.raises(type(exc)):
        pe.call_with_retry(call)
    assert call.call_count == 1
    no_sleep.assert_not_called()


def test_model_error_carries_the_kind_of_failure(settings):
    with mock.patch("litellm.completion", side_effect=RateLimitError("x")), pytest.raises(llm.ModelError) as excinfo:
        llm.complete(llm.ModelConfig(model="openai/example"), [{"role": "user", "content": "Hi"}])
    assert excinfo.value.code == "rate_limited"
    with mock.patch("litellm.completion", side_effect=ValueError("x")), pytest.raises(llm.ModelError) as excinfo:
        llm.complete(llm.ModelConfig(model="openai/example"), [{"role": "user", "content": "Hi"}])
    assert excinfo.value.code == "model_error"


def test_a_rate_limited_model_call_is_retried(settings, no_sleep):
    settings.CHAT_PROVIDER_RETRY_SECONDS = 60
    message = SimpleNamespace(content="Hello", tool_calls=None)
    response = SimpleNamespace(model="m", choices=[SimpleNamespace(message=message)], usage=None)
    with mock.patch("litellm.completion", side_effect=[RateLimitError("x"), response]) as completion:
        result = llm.complete(llm.ModelConfig(model="openai/example"), [{"role": "user", "content": "Hi"}])
    assert result.content == "Hello"
    assert completion.call_count == 2


def test_a_rate_limited_transcription_is_retried(settings, no_sleep):
    settings.CHAT_PROVIDER_RETRY_SECONDS = 60
    settings.CHAT_STT_MODEL = "example/transcriber-1"
    with mock.patch("litellm.transcription", side_effect=[RateLimitError("x"), SimpleNamespace(text="Jambo")]):
        transcript = speech.LiteLLMSpeechToText().transcribe(b"x", content_type="audio/webm")
    assert transcript.text == "Jambo"
    with (
        mock.patch("litellm.transcription", side_effect=ValueError("x")),
        pytest.raises(speech.TranscriptionError) as excinfo,
    ):
        speech.LiteLLMSpeechToText().transcribe(b"x", content_type="audio/webm")
    assert excinfo.value.code == "transcription_error"
