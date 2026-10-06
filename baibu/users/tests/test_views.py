import pytest
from django.core import mail
from django.urls import reverse

from baibu.users.models import AccountDeletionRequest
from baibu.users.models import ConsentRecord
from baibu.users.models import User

pytestmark = pytest.mark.django_db


def test_account_requires_login(client):
    response = client.get(reverse("users:account"))
    assert response.status_code == 302
    assert reverse("account_login") in response.url


def test_account_update(client, user):
    client.force_login(user)
    response = client.post(reverse("users:account"), {"name": "New Name", "city": "Lakeside", "country": "Elsewhere"})
    assert response.status_code == 302
    user.refresh_from_db()
    assert (user.name, user.city, user.country) == ("New Name", "Lakeside", "Elsewhere")


def test_incomplete_profile_is_redirected_to_completion(client, user):
    user.name = ""
    user.save()
    client.force_login(user)
    response = client.get(reverse("users:account"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("users:complete_profile"))


def test_incomplete_profile_can_still_read_terms_and_sign_out(client, user):
    user.name = ""
    user.save()
    client.force_login(user)
    assert client.get(reverse("terms")).status_code == 200
    assert client.get(reverse("account_logout")).status_code == 200


def test_staff_with_incomplete_profile_can_use_admin(client, user):
    user.name = ""
    user.is_staff = True
    user.is_superuser = True
    user.save()
    client.force_login(user)
    assert client.get(reverse("admin:index")).status_code == 200


def test_complete_profile_requires_missing_field_and_returns_to_next(client, user, settings):
    settings.PROFILE_REQUIRED_FIELDS = ["name", "city"]
    user.name = ""
    user.city = ""
    user.save()
    client.force_login(user)
    url = f"{reverse('users:complete_profile')}?next={reverse('users:consent')}"
    response = client.post(url, {"name": "Filled", "city": "", "country": ""})
    assert response.status_code == 200
    assert "city" in response.context["form"].errors
    response = client.post(url, {"name": "Filled", "city": "Riverside", "country": ""})
    assert response.status_code == 302
    assert response.url == reverse("users:consent")


def test_complete_profile_ignores_offsite_next(client, user):
    user.name = ""
    user.save()
    client.force_login(user)
    url = f"{reverse('users:complete_profile')}?next=https://evil.example.com/"
    response = client.post(url, {"name": "Filled", "city": "", "country": ""})
    assert response.url == reverse("users:account")


def test_consent_page_records_choice_once(client, user):
    client.force_login(user)
    assert client.get(reverse("users:consent")).status_code == 200
    client.post(reverse("users:consent"), {"tier": ConsentRecord.Tier.EVAL_ONLY})
    client.post(reverse("users:consent"), {"tier": ConsentRecord.Tier.EVAL_ONLY})
    records = user.consent_records.all()
    assert records.count() == 1
    assert records[0].source == "account_settings"
    client.post(reverse("users:consent"), {"tier": ConsentRecord.Tier.NONE})
    assert user.consent_records.count() == 2


def test_consent_records_consent_text_version(client, user, settings):
    settings.CONSENT_TEXT_VERSION = "2026-10"
    client.force_login(user)
    client.post(reverse("users:consent"), {"tier": ConsentRecord.Tier.TRAINING_ELIGIBLE})
    assert user.consent_records.get().metadata["consent_text_version"] == "2026-10"


def test_deletion_page_names_the_platform(client, user, settings):
    settings.PLATFORM_NAME = "Lugha Yetu"
    client.force_login(user)
    assert "The Lugha Yetu team" in client.get(reverse("users:account_deletion")).text


def test_consent_page_rejects_unknown_tier(client, user):
    client.force_login(user)
    response = client.post(reverse("users:consent"), {"tier": "everything"})
    assert response.status_code == 200
    assert not user.consent_records.exists()


def test_account_deletion_deactivates_signs_out_and_notifies(
    client,
    user,
    settings,
    django_capture_on_commit_callbacks,
):
    settings.ADMINS = [("Ops", "ops@example.org")]
    client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("users:account_deletion"),
            {"confirm": "on", "request_details": "Please remove"},
        )
    assert response.status_code == 200
    deletion_request = AccountDeletionRequest.objects.get(user=user)
    assert str(deletion_request.pk) in response.text
    user.refresh_from_db()
    assert not user.is_active
    assert "_auth_user_id" not in client.session
    assert len(mail.outbox) == 1
    assert "Please remove" not in mail.outbox[0].body
    assert user.email not in mail.outbox[0].body


def test_account_deletion_requires_confirmation(client, user):
    client.force_login(user)
    response = client.post(reverse("users:account_deletion"), {"request_details": ""})
    assert response.status_code == 200
    assert not AccountDeletionRequest.objects.exists()


def test_account_deletion_honeypot_blocks(client, user):
    client.force_login(user)
    client.post(reverse("users:account_deletion"), {"confirm": "on", "website": "http://spam.example"})
    assert not AccountDeletionRequest.objects.exists()


def test_account_deletion_rate_limited(client, user, settings):
    settings.ACCOUNT_DELETION_REQUEST_RATE_LIMIT = 0
    client.force_login(user)
    response = client.post(reverse("users:account_deletion"), {"confirm": "on"})
    assert response.status_code == 200
    # The first request is always allowed; the limit applies to repeats.
    assert AccountDeletionRequest.objects.count() == 1
    user.is_active = True
    user.save()
    client.force_login(user)
    response = client.post(reverse("users:account_deletion"), {"confirm": "on"})
    assert "Too many requests" in response.text


def test_signup_creates_user_with_name(client):
    response = client.post(
        reverse("account_signup"),
        {
            "name": "New Person",
            "email": "new.person@example.org",
            "password1": "a-long-unusual-passphrase",
            "password2": "a-long-unusual-passphrase",
            "accept_terms": "on",
        },
    )
    assert response.status_code == 302
    assert User.objects.get(email="new.person@example.org").name == "New Person"


def test_signup_with_existing_email_in_other_case_creates_no_user(client, user):
    client.post(
        reverse("account_signup"),
        {
            "name": "Someone Else",
            "email": user.email.upper(),
            "password1": "a-long-unusual-passphrase",
            "password2": "a-long-unusual-passphrase",
            "accept_terms": "on",
        },
    )
    assert User.objects.filter(email__iexact=user.email).count() == 1


def test_signup_requires_terms(client):
    response = client.post(
        reverse("account_signup"),
        {
            "name": "New Person",
            "email": "new.person@example.org",
            "password1": "a-long-unusual-passphrase",
            "password2": "a-long-unusual-passphrase",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="new.person@example.org").exists()


def test_signup_honeypot_blocks(client):
    client.post(
        reverse("account_signup"),
        {
            "name": "Bot",
            "email": "bot@example.org",
            "password1": "a-long-unusual-passphrase",
            "password2": "a-long-unusual-passphrase",
            "accept_terms": "on",
            "website": "http://spam.example",
        },
    )
    assert not User.objects.filter(email="bot@example.org").exists()


def test_signup_closed(client, settings):
    settings.ACCOUNT_ALLOW_REGISTRATION = False
    response = client.get(reverse("account_signup"))
    assert "closed" in response.text.lower()


def test_login_page_renders(client):
    assert client.get(reverse("account_login")).status_code == 200
