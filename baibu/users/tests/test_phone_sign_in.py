"""Phone sign-in with one-time codes (PHONE_SIGN_IN_ENABLED).

Numbers come from ranges reserved for fiction: +1 xxx 555 0100-0199 and the
UK drama range +44 7700 900xxx.
"""

import importlib
import re

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import override_settings
from django.urls import clear_url_caches
from django.urls import reverse
from django.urls import set_urlconf

from baibu.users.adapters import AccountAdapter
from baibu.users.forms import UserAdminChangeForm
from baibu.users.messaging import MemoryMessagingProvider
from baibu.users.messaging import MessagingError
from baibu.users.messaging import MessagingProvider
from baibu.users.models import User
from baibu.users.sign_in_config import login_methods
from baibu.users.sign_in_config import signup_fields
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PHONE = "+12015550123"
OTHER_PHONE = "+447700900123"


def _reload_urls():
    import allauth.account.urls
    import allauth.urls

    import config.urls

    for module in (allauth.account.urls, allauth.urls, config.urls):
        importlib.reload(module)
    clear_url_caches()
    set_urlconf(None)


def _phone_settings(*, required=False):
    return override_settings(
        PHONE_SIGN_IN_ENABLED=True,
        PHONE_SIGN_UP_REQUIRED=required,
        ACCOUNT_LOGIN_METHODS=login_methods(phone=True),
        ACCOUNT_SIGNUP_FIELDS=signup_fields(phone=True, phone_required=required),
    )


@pytest.fixture
def phone_sign_in():
    with _phone_settings():
        _reload_urls()
        yield
    _reload_urls()


@pytest.fixture
def phone_sign_up_required():
    with _phone_settings(required=True):
        _reload_urls()
        yield
    _reload_urls()


@pytest.fixture(autouse=True)
def outbox():
    MemoryMessagingProvider.outbox.clear()
    return MemoryMessagingProvider.outbox


@pytest.fixture
def phone_user(db):
    user = UserFactory(phone=PHONE, phone_verified=True)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


def _code(outbox) -> str:
    match = re.search(r"code is (\d{6})\.", outbox[-1].text)
    assert match, outbox[-1].text
    return match.group(1)


# Off by default ---------------------------------------------------------------


def test_off_by_default_no_phone_pages_or_field(client, settings):
    assert settings.PHONE_SIGN_IN_ENABLED is False
    assert {"email"} == settings.ACCOUNT_LOGIN_METHODS
    response = client.get(reverse("account_signup"))
    assert "phone" not in response.context["form"].fields
    assert client.get("/accounts/phone/change/").status_code == 404


def test_off_by_default_account_nav_has_no_phone_link(client, user):
    client.force_login(user)
    assert "/accounts/phone/change/" not in client.get(reverse("users:account")).text


def test_sign_in_settings():
    assert login_methods(phone=False) == {"email"}
    assert signup_fields(phone=False, phone_required=True) == ["email*", "password1*", "password2*"]
    assert signup_fields(phone=True, phone_required=False) == ["email*", "phone", "password1*", "password2*"]
    assert signup_fields(phone=True, phone_required=True) == ["email*", "phone*", "password1*", "password2*"]


# Model ------------------------------------------------------------------------


def test_phone_is_normalised_and_blank_saved_as_null(user):
    user.phone = "+1 (201) 555-0123"
    user.save()
    user.refresh_from_db()
    assert user.phone == PHONE
    user.phone = "  "
    user.phone_verified = True
    user.save(update_fields=["phone"])
    user.refresh_from_db()
    assert user.phone is None
    assert user.phone_verified is False


def test_verified_phone_is_unique():
    UserFactory(phone=PHONE, phone_verified=True)
    with pytest.raises(IntegrityError):
        UserFactory(phone=PHONE, phone_verified=True)


def test_unverified_phone_may_repeat():
    UserFactory(phone=PHONE, phone_verified=True)
    UserFactory(phone=PHONE)
    assert User.objects.filter(phone=PHONE).count() == 2


def test_admin_form_normalises_phone(user):
    form = UserAdminChangeForm(instance=user)
    form.cleaned_data = {"phone": "+1 201 555 0123"}
    assert form.clean_phone() == PHONE
    form.cleaned_data = {"phone": ""}
    assert form.clean_phone() is None


def test_display_identifier_falls_back_to_phone():
    user = UserFactory(name="", phone=PHONE)
    user.email = None
    assert str(user) == PHONE


# Adapter ----------------------------------------------------------------------


def test_adapter_phone_round_trip(user):
    adapter = AccountAdapter()
    assert adapter.get_phone(user) is None
    adapter.set_phone(user, PHONE, False)  # noqa: FBT003
    assert adapter.get_phone(user) == (PHONE, False)
    assert adapter.get_user_by_phone(PHONE) is None
    adapter.set_phone_verified(user, PHONE)
    assert adapter.get_phone(user) == (PHONE, True)
    assert adapter.get_user_by_phone(PHONE) == user


def test_verifying_releases_unverified_claims_by_others(user):
    squatter = UserFactory(phone=PHONE)
    AccountAdapter().set_phone(user, PHONE, True)  # noqa: FBT003
    squatter.refresh_from_db()
    assert squatter.phone is None
    user.refresh_from_db()
    assert (user.phone, user.phone_verified) == (PHONE, True)


def test_adapter_implements_allauth_phone_interface():
    assert AccountAdapter()._has_phone_impl


def test_sms_text_names_the_platform(user, settings, outbox):
    settings.PLATFORM_NAME = "Lugha Yetu"
    AccountAdapter().send_verification_code_sms(user=user, phone=PHONE, code="ABC123")
    assert outbox[-1].phone == PHONE
    assert outbox[-1].text == "Your Lugha Yetu code is ABC123. Do not share it with anyone."


class BrokenProvider(MessagingProvider):
    def send_text(self, phone, text):
        raise MessagingError


def test_provider_failure_tells_the_user(client, phone_sign_in, phone_user, settings):
    settings.MESSAGING_PROVIDER = f"{__name__}.BrokenProvider"
    response = client.post(reverse("account_request_login_code"), {"phone": PHONE}, follow=True)
    assert response.status_code == 200
    assert "could not send a text message" in response.text


def test_provider_failure_outside_a_request_is_only_logged(user, settings):
    settings.MESSAGING_PROVIDER = f"{__name__}.BrokenProvider"
    AccountAdapter().send_verification_code_sms(user=user, phone=PHONE, code="ABC123")


# Sign-in by code ----------------------------------------------------------------


def test_sign_in_with_code_sent_to_phone(client, phone_sign_in, phone_user, outbox):
    response = client.post(reverse("account_request_login_code"), {"phone": "+1 201 555 0123"})
    assert response.status_code == 302
    assert response.url == reverse("account_confirm_login_code")
    assert len(outbox) == 1
    assert outbox[0].phone == PHONE
    response = client.post(reverse("account_confirm_login_code"), {"code": _code(outbox)})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(phone_user.pk)


def test_wrong_code_does_not_sign_in(client, phone_sign_in, phone_user, outbox):
    client.post(reverse("account_request_login_code"), {"phone": PHONE})
    response = client.post(reverse("account_confirm_login_code"), {"code": "000000"})
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_unknown_or_unverified_phone_sends_nothing_and_reveals_nothing(client, phone_sign_in, outbox):
    UserFactory(phone=OTHER_PHONE)  # unverified
    for phone in (PHONE, OTHER_PHONE):
        response = client.post(reverse("account_request_login_code"), {"phone": phone})
        # Same response as for a known number (enumeration prevention).
        assert response.status_code == 302
        assert response.url == reverse("account_confirm_login_code")
    assert outbox == []


def test_invalid_phone_is_refused(client, phone_sign_in, outbox):
    response = client.post(reverse("account_request_login_code"), {"phone": "201 555 0123"})
    assert response.status_code == 200
    assert "international format" in response.text
    assert outbox == []


def test_code_requests_are_rate_limited(client, phone_sign_in, phone_user, outbox):
    for _attempt in range(3):
        client.post(reverse("account_request_login_code"), {"phone": PHONE})
        client.cookies.clear()
    response = client.post(reverse("account_request_login_code"), {"phone": PHONE})
    assert response.status_code == 200
    assert len(outbox) == 3


def test_sign_in_with_phone_and_password(client, phone_sign_in, phone_user):
    response = client.post(
        reverse("account_login"),
        {"login": "+1 201 555 0123", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(phone_user.pk)


def test_email_sign_in_still_works(client, phone_sign_in, phone_user):
    response = client.post(
        reverse("account_login"), {"login": phone_user.email, "password": "correct-horse-battery-staple"}
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(phone_user.pk)


# Sign-up ----------------------------------------------------------------------


def _signup(client, **extra):
    data = {
        "name": "Test Person",
        "email": "newperson@example.org",
        "password1": "a-long-synthetic-passphrase",
        "password2": "a-long-synthetic-passphrase",
        "accept_terms": "on",
        **extra,
    }
    return client.post(reverse("account_signup"), data)


def test_sign_up_without_phone_when_optional(client, phone_sign_in, outbox):
    response = _signup(client)
    assert response.status_code == 302
    user = get_user_model().objects.get(email="newperson@example.org")
    assert user.phone is None
    assert outbox == []


def test_sign_up_with_phone_stores_it_unverified(client, phone_sign_in, outbox):
    _signup(client, phone="+44 7700 900123")
    user = get_user_model().objects.get(email="newperson@example.org")
    assert (user.phone, user.phone_verified) == (OTHER_PHONE, False)


def test_sign_up_requires_phone_when_configured(client, phone_sign_up_required):
    response = _signup(client)
    assert response.status_code == 200
    assert "phone" in response.context["form"].errors


def test_required_phone_is_verified_before_first_sign_in(client, phone_sign_up_required, settings, outbox):
    settings.ACCOUNT_EMAIL_VERIFICATION = "none"
    response = _signup(client, phone=OTHER_PHONE)
    assert response.status_code == 302
    assert response.url == reverse("account_verify_phone")
    assert "_auth_user_id" not in client.session
    response = client.post(reverse("account_verify_phone"), {"code": _code(outbox)})
    assert response.status_code == 302
    user = get_user_model().objects.get(email="newperson@example.org")
    assert user.phone_verified
    assert client.session["_auth_user_id"] == str(user.pk)


# Account settings ---------------------------------------------------------------


def test_account_nav_links_to_phone_page(client, phone_sign_in, user):
    client.force_login(user)
    assert reverse("account_change_phone") in client.get(reverse("users:account")).text


def test_add_phone_in_account_settings(client, phone_sign_in, user, outbox):
    client.force_login(user)
    assert client.get(reverse("account_change_phone")).status_code == 200
    response = client.post(reverse("account_change_phone"), {"phone": "+1 201 555 0123"})
    assert response.status_code == 302
    assert response.url == reverse("account_verify_phone")
    page = client.get(reverse("account_verify_phone"))
    assert page.status_code == 200
    response = client.post(reverse("account_verify_phone"), {"code": _code(outbox)})
    assert response.status_code == 302
    user.refresh_from_db()
    assert (user.phone, user.phone_verified) == (PHONE, True)


def test_cannot_take_another_accounts_verified_phone(client, phone_sign_in, phone_user, user, outbox):
    client.force_login(user)
    client.post(reverse("account_change_phone"), {"phone": PHONE})
    # The code goes to the number's owner, and is refused even if passed on.
    response = client.post(reverse("account_verify_phone"), {"code": _code(outbox)})
    assert response.status_code == 200
    assert "already registered with this phone number" in response.text
    user.refresh_from_db()
    assert user.phone is None
    phone_user.refresh_from_db()
    assert (phone_user.phone, phone_user.phone_verified) == (PHONE, True)


def test_phone_page_shows_status_and_resends_code_for_unverified_number(client, phone_sign_in, user, outbox):
    client.force_login(user)
    assert "Add number" in client.get(reverse("account_change_phone")).text
    AccountAdapter().set_phone(user, PHONE, False)  # noqa: FBT003
    page = client.get(reverse("account_change_phone")).text
    assert PHONE in page
    assert "Not verified" in page
    response = client.post(reverse("account_change_phone"), {"action": "verify"})
    assert response.status_code == 302
    assert outbox[-1].phone == PHONE
    client.post(reverse("account_verify_phone"), {"code": _code(outbox)})
    page = client.get(reverse("account_change_phone")).text
    assert "Verified" in page
    assert "Change number" in page


def test_phone_page_shows_invalid_number_error(client, phone_sign_in, user, outbox):
    client.force_login(user)
    response = client.post(reverse("account_change_phone"), {"phone": "555 0123"})
    assert response.status_code == 200
    assert "international format" in response.text
    assert outbox == []
