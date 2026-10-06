from unittest import mock

import pytest

from baibu.core import storage
from baibu.submissions import services
from baibu.submissions.cleaners import CleanerError
from baibu.submissions.cleaners import CleaningResult
from baibu.submissions.models import Submission
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord

from .factories import SAMPLE_TEXT
from .factories import SubmissionFactory

pytestmark = pytest.mark.django_db


def _all_keys(prefix="submissions"):
    found = []
    dirs, files = storage.private_storage().listdir(prefix)
    found += [f"{prefix}/{name}" for name in files]
    for directory in dirs:
        found += _all_keys(f"{prefix}/{directory}")
    return found


@pytest.fixture
def contributor(user):
    record_consent(user=user, tier=ConsentRecord.Tier.EVAL_ONLY, source="test")
    return user


def _submit(user, text=SAMPLE_TEXT, language_code="en"):
    return services.create_submission(user=user, raw_text=text, language_code=language_code)


class FixedCleaner:
    """Returns a preset result; stands in for any cleaner."""

    result = CleaningResult(text="clean", cleaner="fixed")

    def clean(self, text, *, language_code):
        return self.result


@pytest.fixture
def fixed_cleaner():
    with mock.patch("baibu.submissions.services.get_cleaner", return_value=FixedCleaner()) as patched:
        yield patched.return_value


# --- Creating ---------------------------------------------------------------


def test_create_stores_full_text_privately_and_records_consent(contributor, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        submission = _submit(contributor, text="  " + SAMPLE_TEXT + "\r\n")
    assert submission.status == Submission.Status.PENDING
    assert submission.consent_tier == ConsentRecord.Tier.EVAL_ONLY
    assert submission.consent_record == contributor.consent_records.get()
    assert submission.word_count == 16
    assert submission.excerpt == ""
    raw = storage.read_json(submission.raw_key)
    assert raw["text"] == SAMPLE_TEXT
    assert raw["submission_id"] == str(submission.pk)
    assert "email" not in str(raw)
    assert submission.raw_key.startswith("submissions/raw/")
    # Cleaning is queued only once the row is committed.
    assert len(callbacks) == 1


def test_create_refuses_duplicates_ignoring_spacing(contributor):
    _submit(contributor)
    with pytest.raises(services.DuplicateSubmissionError):
        _submit(contributor, text=SAMPLE_TEXT.replace(" ", "  "))
    assert Submission.objects.count() == 1


def test_create_records_nothing_when_storage_fails(contributor):
    with (
        mock.patch("baibu.core.storage.save_bytes", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        _submit(contributor)
    assert not Submission.objects.exists()


def test_create_removes_stored_text_when_the_row_cannot_be_saved(contributor):
    with (
        mock.patch.object(Submission.objects, "create", side_effect=RuntimeError("db down")),
        pytest.raises(RuntimeError),
    ):
        _submit(contributor)
    assert _all_keys() == []


def test_create_race_on_same_text_reads_as_duplicate(contributor):
    first = _submit(contributor)
    with mock.patch.object(Submission.objects, "filter") as filter_:
        # The duplicate check misses the first row, as in a race.
        filter_.return_value.exists.return_value = False
        with pytest.raises(services.DuplicateSubmissionError):
            _submit(contributor)
    assert _all_keys() == [first.raw_key]


# --- Cleaning ---------------------------------------------------------------


def test_clean_with_rules_verifies_and_stores_redacted_copy(contributor, settings):
    settings.SUBMISSION_EXCERPT_LENGTH = 30
    text = "Write to amina@example.org about the harvest festival next week, everyone is welcome."
    submission = services.run_cleaning(_submit(contributor, text=text))
    assert submission.status == Submission.Status.VERIFIED
    assert submission.cleaner == "rules"
    assert submission.redaction_count == 1
    assert submission.excerpt == "Write to [email] about the har…"
    assert submission.cleaned_at is not None
    clean = storage.read_json(submission.clean_key)
    assert clean["text"].startswith("Write to [email] about")
    # The raw copy is kept separately and unchanged.
    assert "amina@example.org" in storage.read_json(submission.raw_key)["text"]


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (CleaningResult(text="  ", cleaner="fixed"), "Empty"),
        (CleaningResult(text="ok", cleaner="fixed", toxicity_detected=True), "toxic"),
        (CleaningResult(text="ok", cleaner="fixed", quality_score=20), "Quality 20"),
        (CleaningResult(text="ok", cleaner="fixed", detected_language="fr"), "language fr"),
    ],
)
def test_clean_sends_doubtful_text_to_review(contributor, fixed_cleaner, result, reason):
    fixed_cleaner.result = result
    submission = services.run_cleaning(_submit(contributor))
    assert submission.status == Submission.Status.NEEDS_REVIEW
    assert reason in submission.decision_reason


def test_clean_accepts_good_scores_and_matching_language(contributor, fixed_cleaner):
    fixed_cleaner.result = CleaningResult(
        text="ok", cleaner="fixed", quality_score=50, toxicity_detected=False, detected_language="EN"
    )
    assert services.run_cleaning(_submit(contributor)).status == Submission.Status.VERIFIED


def test_cleaner_failure_is_an_issue(contributor):
    with mock.patch("baibu.submissions.cleaners.RuleCleaner.clean", side_effect=CleanerError("Model call failed")):
        submission = services.run_cleaning(_submit(contributor))
    assert submission.status == Submission.Status.ISSUE
    assert submission.decision_reason == "Model call failed"
    assert submission.clean_key == ""


def test_missing_raw_text_is_an_issue(contributor):
    submission = _submit(contributor)
    storage.delete(submission.raw_key)
    submission = services.run_cleaning(submission)
    assert submission.status == Submission.Status.ISSUE
    assert submission.decision_reason == "Raw text is missing."


def test_storage_failure_while_cleaning_is_an_issue_and_leaves_no_file(contributor):
    """TC-SUB-02."""
    submission = _submit(contributor)
    with mock.patch("baibu.core.storage.save_bytes", side_effect=OSError("disk full")):
        submission = services.run_cleaning(submission)
    assert submission.status == Submission.Status.ISSUE
    assert "OSError" in submission.decision_reason
    assert [key for key in _all_keys() if "/clean/" in key] == []


def test_row_failure_after_cleaning_removes_the_clean_file(contributor):
    submission = _submit(contributor)
    with mock.patch.object(Submission, "save", side_effect=RuntimeError("db down")), pytest.raises(RuntimeError):
        services.run_cleaning(submission)
    assert [key for key in _all_keys() if "/clean/" in key] == []


def test_only_pending_submissions_are_cleaned(contributor):
    submission = _submit(contributor)
    submission.status = Submission.Status.REJECTED
    assert services.run_cleaning(submission).clean_key == ""


def test_clean_again_replaces_the_clean_file(contributor, django_capture_on_commit_callbacks):
    submission = services.run_cleaning(_submit(contributor))
    first_key = submission.clean_key
    with django_capture_on_commit_callbacks(execute=True):
        assert services.requeue(submission) is True
    submission.refresh_from_db()
    assert submission.status == Submission.Status.VERIFIED
    assert submission.clean_key != first_key
    assert not storage.exists(first_key)
    assert storage.exists(submission.clean_key)


def test_requeue_respects_transitions(contributor):
    submission = _submit(contributor)
    assert services.requeue(submission) is False


@pytest.mark.parametrize(
    ("start", "allowed", "refused"),
    [
        (Submission.Status.PENDING, Submission.Status.ISSUE, Submission.Status.REJECTED),
        (Submission.Status.NEEDS_REVIEW, Submission.Status.REJECTED, Submission.Status.ISSUE),
        (Submission.Status.REJECTED, Submission.Status.PENDING, Submission.Status.VERIFIED),
    ],
)
def test_status_transitions(start, allowed, refused):
    submission = Submission(status=start)
    assert submission.can_transition_to(allowed)
    assert not submission.can_transition_to(refused)


# --- Deleting ---------------------------------------------------------------


def test_deleting_a_submission_deletes_its_files(contributor, django_capture_on_commit_callbacks):
    submission = services.run_cleaning(_submit(contributor))
    with django_capture_on_commit_callbacks(execute=True):
        submission.delete()
    assert not storage.exists(submission.raw_key)
    assert not storage.exists(submission.clean_key)


def test_deleting_the_user_deletes_their_files(contributor, django_capture_on_commit_callbacks):
    submissions = [SubmissionFactory(user=contributor) for _ in range(2)]
    with django_capture_on_commit_callbacks(execute=True):
        contributor.delete()
    assert not Submission.objects.exists()
    assert not any(storage.exists(s.raw_key) for s in submissions)


def test_task_cleans_and_tolerates_missing_rows(contributor):
    from baibu.submissions.tasks import clean_submission

    submission_id = str(_submit(contributor).pk)
    assert clean_submission(submission_id) == Submission.Status.VERIFIED
    Submission.objects.filter(pk=submission_id).delete()
    assert clean_submission(submission_id) == "missing"
