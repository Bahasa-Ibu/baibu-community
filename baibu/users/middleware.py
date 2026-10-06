from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.urls import reverse


def missing_profile_fields(user) -> list[str]:
    return [field for field in settings.PROFILE_REQUIRED_FIELDS if not getattr(user, field, "")]


class ProfileCompletionMiddleware:
    """Send signed-in users with an incomplete profile to the completion form.

    Which fields are required is set by PROFILE_REQUIRED_FIELDS.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        return self._maybe_redirect(request) or self.get_response(request)

    def _maybe_redirect(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not missing_profile_fields(user):
            return None

        completion_path = reverse("users:complete_profile")
        path = request.path
        exempt_prefixes = [
            completion_path,
            reverse("terms"),
            reverse("privacy"),
            "/health/",
            "/i18n/",
            settings.STATIC_URL,
            settings.MEDIA_URL,
        ]
        # Sign-in and sign-out pages, unprefixed and in every language.
        language_prefixes = ["/", *(f"/{code}/" for code, _name in settings.LANGUAGES)]
        exempt_prefixes += [f"{prefix}accounts/" for prefix in language_prefixes]
        if user.is_staff:
            exempt_prefixes += [f"{prefix}{settings.ADMIN_URL}" for prefix in language_prefixes]
        if any(path.startswith(prefix) for prefix in exempt_prefixes):
            return None
        return HttpResponseRedirect(f"{completion_path}?{urlencode({'next': path})}")
