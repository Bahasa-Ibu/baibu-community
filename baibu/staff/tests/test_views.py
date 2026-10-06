from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from baibu.chat import services as chat_services
from baibu.chat.models import ChatFlag
from baibu.chat.models import Run
from baibu.chat.models import ToolInvocation
from baibu.core import storage
from baibu.submissions.models import Submission
from baibu.submissions.tests.factories import SAMPLE_TEXT
from baibu.submissions.tests.factories import SubmissionFactory
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PAGES = ["staff:dashboard", "staff:submissions", "staff:flags", "staff:errors"]


@pytest.fixture
def staff(client):
    member = UserFactory(is_staff=True)
    client.force_login(member)
    return member


@pytest.fixture
def flag(user):
    record_consent(user=user, tier=ConsentRecord.Tier.EVAL_ONLY, source="test", scope="chat")
    conversation = chat_services.start_conversation(user=user)
    _message, run = chat_services.send_message(conversation=conversation, content="Is it safe?", idempotency_key="k")
    reply = chat_services.execute(run.pk).reply
    return chat_services.report_message(message=reply, user=user, reason="harmful", note="Bad advice")


@pytest.mark.parametrize("name", PAGES)
def test_staff_only(client, user, name):
    url = reverse(name)
    assert reverse("account_login") in client.get(url).url
    client.force_login(user)
    assert client.get(url).status_code == 403


def test_dashboard_counts(client, staff, flag):
    SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    SubmissionFactory(status=Submission.Status.ISSUE)
    page = client.get(reverse("staff:dashboard")).content.decode()
    assert "Submissions to review" in page
    assert "Reported chat replies" in page
    assert page.count('text-3xl font-semibold text-stone-900">1<') == 3


def test_submission_queue_oldest_first_with_filter(client, staff):
    old = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW, decision_reason="Possibly toxic.")
    new = SubmissionFactory(status=Submission.Status.ISSUE, decision_reason="Raw text is missing.")
    SubmissionFactory(status=Submission.Status.VERIFIED, decision_reason="not in queue")
    page = client.get(reverse("staff:submissions")).content.decode()
    assert page.index(str(old.pk)) < page.index(str(new.pk))
    assert "not in queue" not in page
    filtered = client.get(reverse("staff:submissions") + "?status=issue").content.decode()
    assert str(new.pk) in filtered
    assert str(old.pk) not in filtered
    assert client.get(reverse("staff:submissions") + "?status=verified").status_code == 200


def test_empty_queues(client, staff):
    assert "Nothing to review." in client.get(reverse("staff:submissions")).content.decode()
    assert "No open reports." in client.get(reverse("staff:flags")).content.decode()


def test_submission_detail_shows_both_texts(client, staff):
    submission = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    submission.clean_key = storage.save_json("submissions/clean/t.json", {"text": "Cleaned version here."})
    submission.save()
    page = client.get(reverse("staff:submission", args=[submission.pk])).content.decode()
    assert SAMPLE_TEXT in page
    assert "Cleaned version here." in page
    assert 'value="verified"' in page
    assert 'value="rejected"' in page


def test_submission_detail_missing_text(client, staff):
    submission = SubmissionFactory(status=Submission.Status.ISSUE)
    storage.delete(submission.raw_key)
    page = client.get(reverse("staff:submission", args=[submission.pk])).content.decode()
    assert "The stored text is missing." in page
    assert "Not cleaned yet." in page
    # From "issue", accepting is not offered.
    assert 'value="verified"' not in page


def test_decide_moves_to_next_and_notifies(client, staff):
    first = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    second = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    response = client.post(
        reverse("staff:submission", args=[first.pk]), {"decision": "verified", "staff_notes": "Lovely story."}
    )
    assert response.url == reverse("staff:submission", args=[second.pk])
    first.refresh_from_db()
    assert (first.status, first.reviewed_by, first.staff_notes) == ("verified", staff, "Lovely story.")
    assert first.user.notifications.get().kind == "submission_accepted"
    response = client.post(reverse("staff:submission", args=[second.pk]), {"decision": "rejected"})
    assert response.url == reverse("staff:submissions")


def test_second_decision_is_refused(client, staff):
    submission = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    url = reverse("staff:submission", args=[submission.pk])
    # Another reviewer decides between this form's check and the save.
    with mock.patch("baibu.submissions.services.review", return_value=False):
        response = client.post(url, {"decision": "verified"}, follow=True)
    assert "already decided" in response.content.decode()
    submission.refresh_from_db()
    assert submission.status == Submission.Status.NEEDS_REVIEW


def test_decision_must_be_allowed(client, staff):
    submission = SubmissionFactory(status=Submission.Status.ISSUE)
    response = client.post(reverse("staff:submission", args=[submission.pk]), {"decision": "verified"})
    assert response.status_code == 200
    assert "Select a valid choice" in response.content.decode()


def test_clean_again_from_issue(client, staff, django_capture_on_commit_callbacks):
    submission = SubmissionFactory(status=Submission.Status.ISSUE)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("staff:submission", args=[submission.pk]), {"decision": "pending"})
    submission.refresh_from_db()
    assert submission.status == Submission.Status.VERIFIED


def test_flag_queue_and_decision(client, staff, flag):
    page = client.get(reverse("staff:flags")).content.decode()
    assert "Harmful or offensive" in page
    detail = client.get(reverse("staff:flag", args=[flag.pk])).content.decode()
    assert "Is it safe?" in detail
    assert "Bad advice" in detail
    assert "reported" in detail
    response = client.post(reverse("staff:flag", args=[flag.pk]), {"decision": "confirmed", "note": "Removed"})
    assert response.url == reverse("staff:flags")
    flag.refresh_from_db()
    assert (flag.status, flag.decided_by) == (ChatFlag.Status.CONFIRMED, staff)
    again = client.post(reverse("staff:flag", args=[flag.pk]), {"decision": "dismissed"}, follow=True)
    assert "already decided" in again.content.decode()
    decided = client.get(reverse("staff:flag", args=[flag.pk])).content.decode()
    assert "Save and next" not in decided


def test_flag_decision_goes_to_next_open_report(client, staff, flag, user):
    other_reply = flag.conversation.messages.filter(role="assistant").first()
    second = ChatFlag.objects.create(
        conversation=flag.conversation, message=other_reply, reported_by=UserFactory(), reason="other"
    )
    response = client.post(reverse("staff:flag", args=[flag.pk]), {"decision": "dismissed"})
    assert response.url == reverse("staff:flag", args=[second.pk])
    assert client.post(reverse("staff:flag", args=[second.pk]), {}).status_code == 200


def test_errors_page(client, staff, flag, settings):
    SubmissionFactory(status=Submission.Status.ISSUE, decision_reason="Raw text is missing.")
    run = Run.objects.get()
    Run.objects.filter(pk=run.pk).update(status=Run.Status.FAILED, error={"code": "timeout", "message": "slow"})
    ToolInvocation.objects.create(
        run=run, tool_name="internet_search", call_id="1", status="failed", error="Search is down"
    )
    old = ToolInvocation.objects.create(
        run=run, tool_name="internet_search", call_id="2", status="failed", error="Long ago"
    )
    ToolInvocation.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))
    page = client.get(reverse("staff:errors")).content.decode()
    assert "Raw text is missing." in page
    assert "timeout" in page
    assert "Search is down" in page
    assert "Long ago" not in page
    # Plain staff cannot open the admin record; superusers get a link.
    assert reverse("admin:chat_run_change", args=[run.pk]) not in page
    staff.is_superuser = True
    staff.save()
    assert reverse("admin:chat_run_change", args=[run.pk]) in client.get(reverse("staff:errors")).content.decode()


def test_errors_page_empty(client, staff):
    assert client.get(reverse("staff:errors")).content.decode().count("None.") == 3


def test_nav_links_staff_area(client, staff):
    assert reverse("staff:dashboard") in client.get(reverse("home")).content.decode()
