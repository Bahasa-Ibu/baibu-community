import pytest

from baibu.users.models import AccountDeletionRequest
from baibu.users.models import ImmutableRecordError
from baibu.users.models import User
from baibu.users.tests.factories import ConsentRecordFactory

pytestmark = pytest.mark.django_db


def test_create_user_normalises_email():
    user = User.objects.create_user("Person@EXAMPLE.org", "pw-1234567")
    assert user.email == "Person@example.org"
    assert user.check_password("pw-1234567")
    assert not user.is_staff


def test_create_user_without_password_is_unusable():
    assert not User.objects.create_user("nopw@example.org").has_usable_password()


def test_create_user_requires_email():
    with pytest.raises(ValueError, match="email address must be set"):
        User.objects.create_user("  ")


def test_create_superuser_sets_flags():
    admin = User.objects.create_superuser("admin@example.org", "pw-1234567")
    assert admin.is_staff
    assert admin.is_superuser


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_create_superuser_rejects_false_flags(flag):
    with pytest.raises(ValueError, match=flag):
        User.objects.create_superuser("admin@example.org", "pw-1234567", **{flag: False})


def test_blank_email_saved_as_null(user):
    user.email = "   "
    user.save(update_fields=["name"])
    user.refresh_from_db()
    assert user.email is None


def test_display_identifier_falls_back(user):
    assert str(user) == user.name
    user.name = ""
    assert str(user) == user.email
    user.email = None
    assert str(user) == str(user.pk)


def test_absolute_url_is_account_page(user):
    assert user.get_absolute_url() == "/users/account/"


def test_consent_record_cannot_be_edited():
    record = ConsentRecordFactory()
    record.tier = "none"
    with pytest.raises(ImmutableRecordError):
        record.save()


def test_consent_record_cannot_be_deleted():
    record = ConsentRecordFactory()
    with pytest.raises(ImmutableRecordError):
        record.delete()


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        ("submitted", "approved", True),
        ("submitted", "completed", False),
        ("approved", "in_progress", True),
        ("in_progress", "completed", True),
        ("in_progress", "failed", True),
        ("failed", "in_progress", True),
        ("completed", "submitted", False),
        ("rejected", "approved", False),
        ("submitted", "submitted", True),
    ],
)
def test_deletion_request_transitions(current, new, allowed):
    assert AccountDeletionRequest(status=current).can_transition_to(new) is allowed
