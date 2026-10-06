import logging

from allauth.account.fields import PhoneField
from allauth.account.forms import SignupForm
from django import forms
from django.contrib.auth import forms as admin_forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import ConsentRecord
from .models import User
from .phone import normalize_phone
from .phone import validate_e164

logger = logging.getLogger(__name__)

PROFILE_FIELDS = ["name", "city", "country"]


class HoneypotMixin:
    """Adds a hidden field that people leave empty and simple bots fill in."""

    honeypot_field_name = "website"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.honeypot_field_name] = forms.CharField(
            label=_("Website"),
            required=False,
            widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1", "aria-hidden": "true"}),
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get(self.honeypot_field_name):
            logger.info("Form submission blocked by honeypot; form=%s", type(self).__name__)
            self.add_error(
                self.honeypot_field_name,
                forms.ValidationError(_("Leave this field blank."), code="bot_trap"),
            )
        return cleaned_data


class PhoneNumberField(PhoneField):
    """allauth's phone field, normalising the number before validating it."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("validators", [validate_e164])
        kwargs.setdefault("help_text", _("Include the country code, starting with +."))
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        return normalize_phone(super().to_python(value))


class UserSignupForm(HoneypotMixin, SignupForm):
    name = forms.CharField(label=_("Name"), max_length=255)
    accept_terms = forms.BooleanField(
        error_messages={"required": _("You must agree to the terms to create an account.")},
    )

    field_order = ["name", "email", "phone", "password1", "password2", "accept_terms"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["accept_terms"].label = format_html(
            _('I agree to the <a href="{terms_url}">terms of use</a> and <a href="{privacy_url}">privacy notice</a>.'),
            terms_url=reverse("terms"),
            privacy_url=reverse("privacy"),
        )

    def save(self, request):
        user = super().save(request)
        user.name = self.cleaned_data["name"]
        user.save(update_fields=["name"])
        return user


class UserAccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = PROFILE_FIELDS


class ConsentForm(forms.Form):
    tier = forms.ChoiceField(
        label=_("How may your contributions be used?"),
        choices=[
            (
                ConsentRecord.Tier.TRAINING_ELIGIBLE,
                _("To evaluate and to train language tools (models) for my language."),
            ),
            (
                ConsentRecord.Tier.EVAL_ONLY,
                _("Only to test how well language tools work, not to train them."),
            ),
            (ConsentRecord.Tier.NONE, _("Not at all. Do not use my contributions.")),
        ],
        widget=forms.RadioSelect,
    )


class AccountDeletionRequestForm(HoneypotMixin, forms.Form):
    request_details = forms.CharField(
        label=_("Anything we should know? (optional)"),
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    confirm = forms.BooleanField(
        label=_("I understand my account will be deactivated straight away."),
        error_messages={"required": _("Please confirm to continue.")},
    )


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore[name-defined]
        model = User

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get("phone")) or None


class UserAdminCreationForm(forms.ModelForm):
    """Admin form for creating a user with email-only sign-in."""

    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Password confirmation"), widget=forms.PasswordInput)
    email = forms.EmailField(label=_("Email address"), required=True)

    class Meta:
        model = User
        fields = ("email",)

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("The two password fields didn't match."))
        return password2

    def save(self, commit=True):  # noqa: FBT002
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user
