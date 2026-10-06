import pytest
from django.urls import reverse

from baibu.users.account_deletion_requests import capture_account_deletion_request
from baibu.users.models import AccountDeletionRequest
from baibu.users.tests.factories import ConsentRecordFactory
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    admin = UserFactory(email="admin@example.org", is_staff=True, is_superuser=True)
    client.force_login(admin)
    return client


def test_user_changelist_and_change_page(admin_client, user):
    assert admin_client.get(reverse("admin:users_user_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:users_user_change", args=[user.pk])).status_code == 200


def test_admin_can_create_user(admin_client):
    response = admin_client.post(
        reverse("admin:users_user_add"),
        {"email": "created@example.org", "password1": "pw-abc-12345", "password2": "pw-abc-12345"},
    )
    assert response.status_code == 302


def test_admin_create_user_rejects_mismatched_passwords(admin_client):
    response = admin_client.post(
        reverse("admin:users_user_add"),
        {"email": "created@example.org", "password1": "pw-abc-12345", "password2": "different"},
    )
    assert response.status_code == 200


def test_consent_records_are_read_only(admin_client):
    record = ConsentRecordFactory()
    assert admin_client.get(reverse("admin:users_consentrecord_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:users_consentrecord_add")).status_code == 403
    response = admin_client.post(reverse("admin:users_consentrecord_delete", args=[record.pk]), {"post": "yes"})
    assert response.status_code == 403


def _deletion_request(user, **fields):
    request, _ = capture_account_deletion_request(
        source=AccountDeletionRequest.Source.WEB,
        user=user,
        requester_name="Test Person",
        requester_email="person@example.org",
        request_details="Please remove",
    )
    AccountDeletionRequest.objects.filter(pk=request.pk).update(**fields)
    request.refresh_from_db()
    return request


def test_deletion_request_cannot_skip_to_completed(admin_client, user):
    request = _deletion_request(user)
    url = reverse("admin:users_accountdeletionrequest_change", args=[request.pk])
    assert admin_client.get(url).status_code == 200
    response = admin_client.post(url, {"status": "completed", "resolution_notes": ""})
    assert response.status_code == 200
    request.refresh_from_db()
    assert request.status == AccountDeletionRequest.Status.SUBMITTED


def test_completing_deletion_request_sets_completed_at_and_clears_details(admin_client, user):
    request = _deletion_request(user, status=AccountDeletionRequest.Status.IN_PROGRESS)
    url = reverse("admin:users_accountdeletionrequest_change", args=[request.pk])
    response = admin_client.post(url, {"status": "completed", "resolution_notes": "Done"})
    assert response.status_code == 302
    request.refresh_from_db()
    assert request.completed_at is not None
    assert (request.requester_name, request.requester_email, request.request_details) == ("", "", "")


def test_deleting_user_keeps_receipt(admin_client, user):
    request = _deletion_request(user, status=AccountDeletionRequest.Status.COMPLETED)
    user.delete()
    request.refresh_from_db()
    assert request.user is None


def test_mark_completed_action(admin_client, user):
    request = _deletion_request(user, status=AccountDeletionRequest.Status.IN_PROGRESS)
    admin_client.post(
        reverse("admin:users_accountdeletionrequest_changelist"),
        {"action": "mark_completed", "_selected_action": [str(request.pk)]},
    )
    request.refresh_from_db()
    assert request.status == AccountDeletionRequest.Status.COMPLETED
    assert request.completed_at is not None
    assert request.requester_email == ""


def test_mark_completed_action_skips_requests_not_in_progress(admin_client, user):
    request = _deletion_request(user)
    admin_client.post(
        reverse("admin:users_accountdeletionrequest_changelist"),
        {"action": "mark_completed", "_selected_action": [str(request.pk)]},
    )
    request.refresh_from_db()
    assert request.status == AccountDeletionRequest.Status.SUBMITTED
