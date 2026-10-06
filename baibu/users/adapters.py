from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils.translation import gettext

from . import messaging
from .models import User
from .phone import normalize_phone


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return settings.ACCOUNT_ALLOW_REGISTRATION

    # Phone sign-in. allauth only calls these when PHONE_SIGN_IN_ENABLED puts
    # "phone" in ACCOUNT_LOGIN_METHODS and ACCOUNT_SIGNUP_FIELDS.

    def phone_form_field(self, **kwargs):
        from .forms import PhoneNumberField

        return PhoneNumberField(**kwargs)

    def get_phone(self, user: User) -> tuple[str, bool] | None:
        return (user.phone, user.phone_verified) if user.phone else None

    def set_phone(self, user: User, phone: str, verified: bool) -> None:  # noqa: FBT001
        if verified:
            self.set_phone_verified(user, phone)
            return
        user.phone = phone
        user.phone_verified = False
        user.save(update_fields=["phone", "phone_verified"])

    def set_phone_verified(self, user: User, phone: str) -> None:
        with transaction.atomic():
            # Someone else may have typed this number without verifying it.
            User.objects.filter(phone=phone, phone_verified=False).exclude(pk=user.pk).update(phone=None)
            user.phone = phone
            user.phone_verified = True
            user.save(update_fields=["phone", "phone_verified"])

    def get_user_by_phone(self, phone: str) -> User | None:
        # Only a verified number identifies an account. Sign-in with a password
        # passes the number as typed, so normalise it here too.
        return User.objects.filter(phone=normalize_phone(phone), phone_verified=True).first()

    def send_verification_code_sms(self, user: User, phone: str, code: str, **kwargs) -> None:
        text = render_to_string(
            "users/messages/verification_code.txt",
            {"code": code, "user": user, "platform_name": settings.PLATFORM_NAME},
            request=self.request,
        ).strip()
        try:
            messaging.send_text(phone, text)
        except messaging.MessagingError:
            if self.request is not None:
                messages.error(
                    self.request,
                    gettext("We could not send a text message to that number. Please try again later."),
                )
