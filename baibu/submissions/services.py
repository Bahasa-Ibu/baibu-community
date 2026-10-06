"""Creating submissions and applying cleaning results."""

import logging
import uuid

from django.conf import settings
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from baibu.core import storage
from baibu.users.consent import consent_state

from . import text as text_rules
from .cleaners import CleanerError
from .cleaners import CleaningResult
from .cleaners import get_cleaner
from .models import Submission

logger = logging.getLogger(__name__)

RAW_AREA = "submissions/raw"
CLEAN_AREA = "submissions/clean"


class DuplicateSubmissionError(Exception):
    pass


def create_submission(*, user, raw_text: str, language_code: str, source: str = "web") -> Submission:
    """Store the full text privately, record the submission and queue cleaning.

    Raises ``DuplicateSubmissionError`` if the same text was submitted before,
    and lets storage errors through (nothing is recorded then).
    """
    from .tasks import clean_submission

    raw_text = text_rules.normalise(raw_text)
    digest = text_rules.content_hash(raw_text)
    if Submission.objects.filter(content_hash=digest).exists():
        raise DuplicateSubmissionError
    consent = consent_state(user=user, scope=settings.SUBMISSION_CONSENT_SCOPE)
    submission_id = uuid.uuid7()
    raw_key = storage.save_json(
        storage.build_key(RAW_AREA, f"{submission_id}.json"),
        {
            "schema": "submission.raw.v1",
            "submission_id": str(submission_id),
            "language_code": language_code,
            "source": source,
            "received_at": timezone.now().isoformat(),
            "text": raw_text,
        },
    )
    try:
        with transaction.atomic():
            submission = Submission.objects.create(
                id=submission_id,
                user=user,
                language_code=language_code,
                consent_tier=consent.tier,
                consent_record=consent.latest_record,
                raw_key=raw_key,
                content_hash=digest,
                word_count=text_rules.word_count(raw_text),
                character_count=len(raw_text),
            )
    except IntegrityError as exc:
        # The same text arrived at the same moment.
        storage.delete(raw_key)
        raise DuplicateSubmissionError from exc
    except Exception:
        storage.delete(raw_key)
        raise
    transaction.on_commit(lambda: clean_submission.delay(str(submission.pk)))
    return submission


def decide(submission: Submission, result: CleaningResult) -> tuple[str, str]:
    """Return the status and reason for a cleaning result."""
    if not result.text.strip():
        return Submission.Status.NEEDS_REVIEW, "Empty after cleaning."
    if result.toxicity_detected:
        return Submission.Status.NEEDS_REVIEW, "Possibly toxic."
    minimum = settings.SUBMISSION_MIN_QUALITY
    if result.quality_score is not None and result.quality_score < minimum:
        return Submission.Status.NEEDS_REVIEW, f"Quality {result.quality_score} below {minimum}."
    if result.detected_language and result.detected_language.lower() != submission.language_code.lower():
        return Submission.Status.NEEDS_REVIEW, f"Detected language {result.detected_language}."
    return Submission.Status.VERIFIED, ""


def _mark_issue(submission: Submission, reason: str) -> Submission:
    logger.warning("Submission %s could not be cleaned: %s", submission.pk, reason)
    submission.status = Submission.Status.ISSUE
    submission.decision_reason = reason[:512]
    submission.save(update_fields=["status", "decision_reason", "updated_at"])
    return submission


def run_cleaning(submission: Submission) -> Submission:
    """Clean a pending submission and record the outcome."""
    if submission.status != Submission.Status.PENDING:
        return submission
    raw = storage.read_json(submission.raw_key)
    if not raw or not isinstance(raw.get("text"), str):
        return _mark_issue(submission, "Raw text is missing.")
    try:
        result = get_cleaner().clean(raw["text"], language_code=submission.language_code)
    except CleanerError as exc:
        return _mark_issue(submission, str(exc))
    status, reason = decide(submission, result)
    try:
        clean_key = storage.save_json(
            storage.build_key(CLEAN_AREA, f"{submission.pk}.json"),
            {
                "schema": "submission.clean.v1",
                "submission_id": str(submission.pk),
                "language_code": submission.language_code,
                "cleaner": result.cleaner,
                "cleaned_at": timezone.now().isoformat(),
                "text": result.text,
            },
        )
    except Exception as exc:
        logger.exception("Could not store cleaned text for submission %s", submission.pk)
        return _mark_issue(submission, f"Could not store cleaned text: {type(exc).__name__}")

    old_clean_key = submission.clean_key
    submission.status = status
    submission.decision_reason = reason
    submission.clean_key = clean_key
    limit = settings.SUBMISSION_EXCERPT_LENGTH
    submission.excerpt = result.text if len(result.text) <= limit else result.text[:limit].rstrip() + "…"
    submission.cleaner = result.cleaner
    submission.redaction_count = result.redaction_count
    submission.toxicity_detected = result.toxicity_detected
    submission.quality_score = result.quality_score
    submission.detected_language = result.detected_language
    submission.flags = result.flags
    submission.cleaned_at = timezone.now()
    try:
        submission.save()
    except Exception:
        storage.delete(clean_key)
        raise
    if old_clean_key and old_clean_key != clean_key:
        transaction.on_commit(lambda: storage.delete(old_clean_key))
    return submission


def requeue(submission: Submission) -> bool:
    """Send a submission back for cleaning ("clean again")."""
    from .tasks import clean_submission

    if not submission.can_transition_to(Submission.Status.PENDING):
        return False
    submission.status = Submission.Status.PENDING
    submission.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: clean_submission.delay(str(submission.pk)))
    return True


def delete_files(submission: Submission) -> None:
    for key in (submission.raw_key, submission.clean_key):
        if key:
            storage.delete(key)
