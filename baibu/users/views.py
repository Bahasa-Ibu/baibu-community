import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.cache import cache
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.crypto import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods
from django.views.generic import UpdateView

from .account_deletion_requests import capture_account_deletion_request
from .consent import consent_state
from .consent import record_consent
from .forms import AccountDeletionRequestForm
from .forms import ConsentForm
from .forms import UserAccountForm
from .middleware import missing_profile_fields
from .models import AccountDeletionRequest
from .models import User

logger = logging.getLogger(__name__)


class UserAccountView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserAccountForm
    template_name = "users/account.html"
    success_message = _("Your profile was updated.")

    def get_object(self, queryset=None) -> User:
        return self.request.user

    def get_success_url(self) -> str:
        return reverse("users:account")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["consent_state"] = consent_state(user=self.request.user)
        return context


account_view = cache_control(private=True, no_store=True)(UserAccountView.as_view())


class CompleteProfileView(UserAccountView):
    template_name = "users/complete_profile.html"
    success_message = _("Thanks, your profile is complete.")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field in missing_profile_fields(self.request.user):
            form.fields[field].required = True
        return form

    def get_success_url(self) -> str:
        next_url = self.request.GET.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return next_url
        return reverse("users:account")


complete_profile_view = cache_control(private=True, no_store=True)(CompleteProfileView.as_view())


@login_required
@cache_control(private=True, no_store=True)
@require_http_methods(["GET", "POST"])
def consent_view(request: HttpRequest) -> HttpResponse:
    state = consent_state(user=request.user)
    form = ConsentForm(request.POST or None, initial={"tier": state.tier if state.latest_record else None})
    if request.method == "POST" and form.is_valid():
        new_tier = form.cleaned_data["tier"]
        if state.latest_record is None or new_tier != state.tier:
            record_consent(
                user=request.user,
                tier=new_tier,
                source="account_settings",
                metadata={
                    "locale": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE),
                    "consent_text_version": settings.CONSENT_TEXT_VERSION,
                },
            )
        messages.success(request, _("Your choice was saved."))
        return redirect("users:consent")
    history = request.user.consent_records.filter(scope=settings.CONSENT_DEFAULT_SCOPE)[:20]
    return render(request, "users/consent.html", {"form": form, "consent_state": state, "history": history})


@login_required
@cache_control(private=True, no_store=True)
@require_http_methods(["GET", "POST"])
def account_deletion_view(request: HttpRequest) -> HttpResponse:
    form = AccountDeletionRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _deletion_rate_limited(request):
            form.add_error(None, _("Too many requests. Please wait before trying again."))
        else:
            deletion_request, _created = capture_account_deletion_request(
                source=AccountDeletionRequest.Source.IN_APP,
                user=request.user,
                requester_name=request.user.name,
                requester_email=request.user.email or "",
                request_details=form.cleaned_data["request_details"],
                metadata={"locale": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)},
            )
            # The account is now inactive, so end the session.
            logout(request)
            return render(request, "users/account_deletion_done.html", {"receipt_id": deletion_request.pk})
    return render(request, "users/account_deletion.html", {"form": form})


def _deletion_rate_limited(request: HttpRequest) -> bool:
    digest = salted_hmac("account-deletion-rate", f"user:{request.user.pk}").hexdigest()
    key = f"account-deletion-rate:{digest}"
    try:
        if cache.add(key, 1, timeout=settings.ACCOUNT_DELETION_REQUEST_RATE_WINDOW_SECONDS):
            return False
        count = cache.incr(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Account deletion rate limiter unavailable; error_type=%s", type(exc).__name__)
        return False
    return count > settings.ACCOUNT_DELETION_REQUEST_RATE_LIMIT
