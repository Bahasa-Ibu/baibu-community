"""Cleaners: the pluggable step that checks and cleans submitted text.

Every submission first goes through the rules in :mod:`.text`. The cleaner
named by ``SUBMISSION_CLEANER`` then runs on the result:

- ``RuleCleaner`` (default): the rules only. No model, no network.
- ``LiteLLMCleaner``: asks a language model, through LiteLLM, to redact
  remaining personal data and rate toxicity and quality. The deployment
  chooses the model and endpoint (``SUBMISSION_CLEANER_MODEL`` and friends).
- ``MockCleaner``: deterministic stand-in for a model, for tests and demos.

A cleaner returns a :class:`CleaningResult` or raises :class:`CleanerError`.
"""

import json
import re
from dataclasses import dataclass
from dataclasses import field
from functools import cache

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.module_loading import import_string

from . import text as text_rules


class CleanerError(Exception):
    """The cleaner could not produce a result (for example, the model failed)."""


@dataclass
class CleaningResult:
    text: str
    cleaner: str
    redaction_count: int = 0
    toxicity_detected: bool | None = None
    quality_score: int | None = None
    detected_language: str = ""
    flags: list[str] = field(default_factory=list)


class Cleaner:
    name = "cleaner"

    def clean(self, text: str, *, language_code: str) -> CleaningResult:
        raise NotImplementedError


def apply_rules(raw_text: str) -> text_rules.Redacted:
    return text_rules.redact(text_rules.normalise(raw_text))


class RuleCleaner(Cleaner):
    """Normalisation and pattern redaction only."""

    name = "rules"

    def clean(self, text: str, *, language_code: str) -> CleaningResult:
        ruled = apply_rules(text)
        return CleaningResult(text=ruled.text, cleaner=self.name, redaction_count=ruled.total)


class MockCleaner(RuleCleaner):
    """Behaves like a model cleaner without calling one.

    Text containing a word from ``toxic_words`` is flagged as toxic; the
    quality score grows with length; the language is echoed back.
    """

    name = "mock"
    toxic_words = frozenset({"mocktoxic"})

    def clean(self, text: str, *, language_code: str) -> CleaningResult:
        result = super().clean(text, language_code=language_code)
        words = {w.strip(".,!?;:").lower() for w in result.text.split()}
        result.toxicity_detected = bool(words & self.toxic_words)
        result.quality_score = min(100, 10 * text_rules.word_count(result.text))
        result.detected_language = language_code
        result.cleaner = self.name
        return result


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LiteLLMCleaner(RuleCleaner):
    """Rules first, then a language model reached through LiteLLM.

    The instructions come from the template ``submissions/cleaner_prompt.txt``,
    which a deployment can override. The model must answer with one JSON
    object: ``text``, ``redactions``, ``toxic``, ``quality``, ``language``.
    """

    name = "litellm"

    def clean(self, text: str, *, language_code: str) -> CleaningResult:
        import litellm

        ruled = super().clean(text, language_code=language_code)
        model = settings.SUBMISSION_CLEANER_MODEL
        if not model:
            msg = "SUBMISSION_CLEANER_MODEL is not set."
            raise CleanerError(msg)
        prompt = render_to_string("submissions/cleaner_prompt.txt", {"language_code": language_code})
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": ruled.text}],
                api_base=settings.SUBMISSION_CLEANER_API_BASE or None,
                api_key=settings.SUBMISSION_CLEANER_API_KEY or None,
                timeout=settings.SUBMISSION_CLEANER_TIMEOUT,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            msg = f"Model call failed: {type(exc).__name__}"
            raise CleanerError(msg) from exc
        answer = _parse_answer(content)
        return CleaningResult(
            text=text_rules.normalise(answer["text"]),
            cleaner=f"{self.name}:{getattr(response, 'model', None) or model}"[:128],
            redaction_count=ruled.redaction_count + answer["redactions"],
            toxicity_detected=answer["toxic"],
            quality_score=answer["quality"],
            detected_language=answer["language"],
        )


def _parse_answer(content: str) -> dict:
    match = _JSON_BLOCK.search(content)
    try:
        data = json.loads(match.group(0) if match else content)
    except json.JSONDecodeError as exc:
        msg = "Model answer is not JSON."
        raise CleanerError(msg) from exc
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        msg = "Model answer has no text."
        raise CleanerError(msg)
    quality = data.get("quality")
    redactions = data.get("redactions")
    return {
        "text": data["text"],
        "redactions": redactions if isinstance(redactions, int) and redactions >= 0 else 0,
        "toxic": data["toxic"] if isinstance(data.get("toxic"), bool) else None,
        "quality": max(0, min(100, quality)) if isinstance(quality, int) and not isinstance(quality, bool) else None,
        "language": str(data.get("language") or "")[:24],
    }


@cache
def _cleaner_class(path: str) -> type[Cleaner]:
    return import_string(path)


def get_cleaner() -> Cleaner:
    return _cleaner_class(settings.SUBMISSION_CLEANER)()
