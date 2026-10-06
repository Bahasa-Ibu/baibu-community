from unittest import mock

import pytest
from django.urls import reverse

from baibu.core import storage
from baibu.submissions.models import Submission
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory

from .factories import SAMPLE_TEXT
from .factories import SubmissionFactory

pytestmark = pytest.mark.django_db

CREATE_URL = reverse("submissions:create")
LIST_URL = reverse("submissions:list")


@pytest.fixture
def contributor(client, user):
    record_consent(user=user, tier=ConsentRecord.Tier.EVAL_ONLY, source="test")
    client.force_login(user)
    return user


def _post(client, **data):
    return client.post(CREATE_URL, {"language_code": "en", "text": SAMPLE_TEXT, "confirm": "on", **data})


def test_pages_require_sign_in(client):
    for url in (CREATE_URL, LIST_URL):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("account_login") in response.url


def test_contributing_requires_consent(client, user):
    client.force_login(user)
    response = client.get(CREATE_URL)
    assert response.status_code == 302
    assert response.url == reverse("users:consent")
    record_consent(user=user, tier=ConsentRecord.Tier.NONE, source="test")
    assert client.get(CREATE_URL).status_code == 302


def test_single_language_is_not_asked(client, contributor, settings):
    settings.SUBMISSION_LANGUAGES = ["en"]
    response = client.get(CREATE_URL)
    assert response.status_code == 200
    assert 'type="hidden" name="language_code" value="en"' in response.content.decode()


def test_several_languages_are_offered(client, contributor, settings):
    settings.SUBMISSION_LANGUAGES = ["en", "fr"]
    content = client.get(CREATE_URL).content.decode()
    assert '<select name="language_code"' in content
    assert "français" in content


def test_submit_queues_cleaning_and_shows_result(client, contributor, django_capture_on_commit_callbacks):
    """TC-SUB-01, with the default rule cleaner."""
    text = "Ask for   Amina at amina@example.org\x07 if the market moves to the new square next month."
    with django_capture_on_commit_callbacks(execute=True):
        response = _post(client, text=text)
    assert response.status_code == 302
    assert response.url == LIST_URL
    submission = Submission.objects.get()
    assert submission.user == contributor
    assert submission.consent_tier == ConsentRecord.Tier.EVAL_ONLY
    assert submission.status == Submission.Status.VERIFIED
    assert storage.read_json(submission.clean_key)["text"] == (
        "Ask for Amina at [email] if the market moves to the new square next month."
    )
    assert "amina@example.org" in storage.read_json(submission.raw_key)["text"]
    page = client.get(LIST_URL).content.decode()
    assert "Ask for Amina at [email]" in page
    assert "Verified" in page


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"text": "Too short to keep."}, "at least 10 words"),
        ({"confirm": ""}, "Please confirm"),
        ({"language_code": "xx"}, "Select a valid choice"),
    ],
)
def test_invalid_submissions_are_refused(client, contributor, settings, data, error):
    settings.SUBMISSION_LANGUAGES = ["en", "fr"]
    response = _post(client, **data)
    assert response.status_code == 200
    assert error in response.content.decode()
    assert not Submission.objects.exists()


def test_overlong_text_is_refused(client, contributor, settings):
    settings.SUBMISSION_MAX_CHARACTERS = 50
    response = _post(client)
    assert "under 50 characters" in response.content.decode()


def test_duplicate_text_is_refused(client, contributor):
    _post(client)
    response = _post(client, text=f"  {SAMPLE_TEXT.replace(' ', '   ')}\n")
    assert "already been submitted" in response.content.decode()
    assert Submission.objects.count() == 1


def test_storage_outage_shows_a_message(client, contributor):
    with mock.patch("baibu.core.storage.save_bytes", side_effect=OSError("down")):
        response = _post(client)
    assert response.status_code == 200
    assert "could not save your writing" in response.content.decode()
    assert not Submission.objects.exists()


def test_list_shows_only_own_submissions(client, contributor):
    SubmissionFactory(user=contributor, excerpt="Mine, about the river.")
    SubmissionFactory(user=UserFactory(), excerpt="Someone else's story.")
    pending = SubmissionFactory(user=contributor)
    page = client.get(LIST_URL).content.decode()
    assert "Mine, about the river." in page
    assert "Someone else" not in page
    assert "Being checked." in page
    assert str(pending.pk) in page


def test_empty_list(client, contributor):
    assert "not contributed anything yet" in client.get(LIST_URL).content.decode()


def test_delete_own_submission_removes_files(client, contributor, django_capture_on_commit_callbacks):
    submission = SubmissionFactory(user=contributor)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("submissions:delete", args=[submission.pk]))
    assert response.status_code == 302
    assert not Submission.objects.exists()
    assert not storage.exists(submission.raw_key)


def test_cannot_delete_someone_elses_submission(client, contributor):
    other = SubmissionFactory(user=UserFactory())
    assert client.post(reverse("submissions:delete", args=[other.pk])).status_code == 404
    assert client.get(reverse("submissions:delete", args=[other.pk])).status_code == 405
    assert Submission.objects.filter(pk=other.pk).exists()


def test_nav_links_to_contributions(client, contributor):
    assert LIST_URL in client.get(reverse("home")).content.decode()
