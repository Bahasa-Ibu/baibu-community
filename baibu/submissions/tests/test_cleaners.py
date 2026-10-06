import json
from types import SimpleNamespace
from unittest import mock

import pytest

from baibu.submissions import cleaners
from baibu.submissions.cleaners import CleanerError
from baibu.submissions.cleaners import LiteLLMCleaner
from baibu.submissions.cleaners import MockCleaner
from baibu.submissions.cleaners import RuleCleaner


def _response(content, model="example/model-1"):
    return SimpleNamespace(model=model, choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def model_settings(settings):
    settings.SUBMISSION_CLEANER_MODEL = "openai/example-model"
    settings.SUBMISSION_CLEANER_API_BASE = "http://llm.example.org/v1"
    settings.SUBMISSION_CLEANER_API_KEY = "test-key"
    return settings


def test_rule_cleaner_normalises_and_redacts():
    result = RuleCleaner().clean("Mail  me at x@example.org ", language_code="en")
    assert result.text == "Mail me at [email]"
    assert result.redaction_count == 1
    assert result.cleaner == "rules"
    assert result.toxicity_detected is None
    assert result.quality_score is None


def test_mock_cleaner_flags_marker_word_and_scores_length():
    result = MockCleaner().clean("one two three mocktoxic.", language_code="sw")
    assert result.toxicity_detected is True
    assert result.quality_score == 40
    assert result.detected_language == "sw"
    assert MockCleaner().clean("a b c d e f g h i j k l", language_code="en").quality_score == 100


@pytest.mark.django_db
def test_litellm_cleaner_sends_rule_cleaned_text_and_reads_answer(model_settings):
    answer = {"text": "Met [name] by the well.", "redactions": 1, "toxic": False, "quality": 82, "language": "en"}
    with mock.patch("litellm.completion", return_value=_response(json.dumps(answer))) as completion:
        result = LiteLLMCleaner().clean("Met Jo by the well. x@example.org", language_code="en")
    kwargs = completion.call_args.kwargs
    assert kwargs["model"] == "openai/example-model"
    assert kwargs["api_base"] == "http://llm.example.org/v1"
    assert kwargs["api_key"] == "test-key"
    # The model only sees text the rules already cleaned.
    assert kwargs["messages"][1]["content"] == "Met Jo by the well. [email]"
    assert '"en"' in kwargs["messages"][0]["content"]
    assert result.text == "Met [name] by the well."
    assert result.redaction_count == 2
    assert (result.toxicity_detected, result.quality_score, result.detected_language) == (False, 82, "en")
    assert result.cleaner == "litellm:example/model-1"


@pytest.mark.django_db
def test_litellm_cleaner_accepts_fenced_json_and_clamps_values(model_settings):
    content = '```json\n{"text": "Hello there", "quality": 140, "redactions": -2, "toxic": "no"}\n```'
    with mock.patch("litellm.completion", return_value=_response(content)):
        result = LiteLLMCleaner().clean("Hello there", language_code="en")
    assert result.quality_score == 100
    assert result.redaction_count == 0
    assert result.toxicity_detected is None
    assert result.detected_language == ""


@pytest.mark.django_db
@pytest.mark.parametrize("content", ["not json at all", '{"quality": 50}', "[1, 2]"])
def test_litellm_cleaner_rejects_unusable_answers(model_settings, content):
    with mock.patch("litellm.completion", return_value=_response(content)), pytest.raises(CleanerError):
        LiteLLMCleaner().clean("Hello there", language_code="en")


@pytest.mark.django_db
def test_litellm_cleaner_wraps_model_errors(model_settings):
    with (
        mock.patch("litellm.completion", side_effect=TimeoutError("slow")),
        pytest.raises(CleanerError, match="TimeoutError"),
    ):
        LiteLLMCleaner().clean("Hello there", language_code="en")


def test_litellm_cleaner_needs_a_model(settings):
    settings.SUBMISSION_CLEANER_MODEL = ""
    with pytest.raises(CleanerError, match="SUBMISSION_CLEANER_MODEL"):
        LiteLLMCleaner().clean("Hello there", language_code="en")


def test_base_cleaner_is_abstract():
    with pytest.raises(NotImplementedError):
        cleaners.Cleaner().clean("x", language_code="en")


def test_get_cleaner_follows_setting(settings):
    settings.SUBMISSION_CLEANER = "baibu.submissions.cleaners.MockCleaner"
    assert isinstance(cleaners.get_cleaner(), MockCleaner)
