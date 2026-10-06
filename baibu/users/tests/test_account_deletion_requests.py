from unittest import mock

import pytest
from django.core import mail

from baibu.users.account_deletion_requests import _notify_operations_safely
from baibu.users.account_deletion_requests import capture_account_deletion_request
from baibu.users.models import AccountDeletionRequest
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db
Source = AccountDeletionRequest.Source


def test_capture_normalises_and_deactivates(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        request, created = capture_account_deletion_request(
            source=Source.WEB,
            user=user,
            requester_name="  Spaced   Name ",
            requester_email="Someone@EXAMPLE.org",
            request_details="  details  ",
        )
    assert created
    assert request.requester_name == "Spaced Name"
    assert request.requester_email == "Someone@example.org"
    assert request.request_details == "details"
    user.refresh_from_db()
    assert not user.is_active


def test_second_request_returns_open_one(user):
    first, _ = capture_account_deletion_request(source=Source.WEB, user=user)
    second, created = capture_account_deletion_request(source=Source.IN_APP, user=user)
    assert not created
    assert second.pk == first.pk


def test_new_request_allowed_after_completion(user):
    first, _ = capture_account_deletion_request(source=Source.WEB, user=user)
    first.status = AccountDeletionRequest.Status.COMPLETED
    first.save()
    second, created = capture_account_deletion_request(source=Source.WEB, user=user)
    assert created
    assert second.pk != first.pk


def test_notification_goes_to_operations_group(user, django_capture_on_commit_callbacks):
    from django.contrib.auth.models import Group

    group = Group.objects.create(name="operations-email")
    UserFactory(email="ops@example.org").groups.add(group)
    with django_capture_on_commit_callbacks(execute=True):
        capture_account_deletion_request(source=Source.WEB, user=user)
    assert mail.outbox[0].to == ["ops@example.org"]


def test_no_recipients_sends_nothing(user, settings, django_capture_on_commit_callbacks):
    settings.ADMINS = []
    with django_capture_on_commit_callbacks(execute=True):
        capture_account_deletion_request(source=Source.WEB, user=user)
    assert mail.outbox == []


def test_notification_failure_is_logged_not_raised(user, caplog):
    request, _ = capture_account_deletion_request(source=Source.WEB, user=user)
    with mock.patch("baibu.users.account_deletion_requests._notify_operations", side_effect=OSError("smtp down")):
        _notify_operations_safely(request.pk)
    assert "notification failed" in caplog.text
