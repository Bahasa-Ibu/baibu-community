import pytest
from django.urls import reverse

from baibu.submissions.models import Submission
from baibu.users.tests.factories import UserFactory

from .factories import SAMPLE_TEXT
from .factories import SubmissionFactory

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:submissions_submission_changelist")


@pytest.fixture
def staff_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


def _action(client, action, *submissions):
    return client.post(
        CHANGELIST, {"action": action, "_selected_action": [str(s.pk) for s in submissions]}, follow=True
    )


def test_change_page_shows_stored_text(staff_client):
    submission = SubmissionFactory()
    response = staff_client.get(reverse("admin:submissions_submission_change", args=[submission.pk]))
    content = response.content.decode()
    assert response.status_code == 200
    assert SAMPLE_TEXT in content
    # No cleaned file yet.
    assert "—" in content


def test_changelist_and_no_manual_add(staff_client):
    SubmissionFactory()
    assert staff_client.get(CHANGELIST).status_code == 200
    assert staff_client.get(reverse("admin:submissions_submission_add")).status_code == 403


def test_staff_can_only_edit_notes(staff_client):
    submission = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    url = reverse("admin:submissions_submission_change", args=[submission.pk])
    staff_client.post(url, {"staff_notes": "Checked by hand.", "status": Submission.Status.VERIFIED})
    submission.refresh_from_db()
    assert submission.staff_notes == "Checked by hand."
    assert submission.status == Submission.Status.NEEDS_REVIEW


def test_review_actions_follow_transitions(staff_client):
    review = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    pending = SubmissionFactory(status=Submission.Status.PENDING)
    response = _action(staff_client, "mark_rejected", review, pending)
    content = response.content.decode()
    assert "1 submission updated." in content
    assert "1 submission skipped" in content
    review.refresh_from_db()
    pending.refresh_from_db()
    assert review.status == Submission.Status.REJECTED
    assert pending.status == Submission.Status.PENDING

    _action(staff_client, "mark_verified", review)
    review.refresh_from_db()
    assert review.status == Submission.Status.REJECTED


def test_clean_again(staff_client, django_capture_on_commit_callbacks):
    issue = SubmissionFactory(status=Submission.Status.ISSUE)
    with django_capture_on_commit_callbacks(execute=True):
        response = _action(staff_client, "clean_again", issue)
    assert "1 submission queued." in response.content.decode()
    issue.refresh_from_db()
    assert issue.status == Submission.Status.VERIFIED
