from django.conf import settings
from django.core.checks import Tags
from django.core.checks import Warning  # noqa: A004
from django.core.checks import register


@register(Tags.security, deploy=True)
def phone_sign_in_provider_check(app_configs, **kwargs):
    """Warn when phone sign-in is on but codes would only be logged."""
    if settings.PHONE_SIGN_IN_ENABLED and settings.MESSAGING_PROVIDER.endswith(".ConsoleMessagingProvider"):
        return [
            Warning(
                "PHONE_SIGN_IN_ENABLED is on, but MESSAGING_PROVIDER is the console provider: "
                "sign-in codes are written to the log, not sent.",
                hint="Set MESSAGING_PROVIDER to your own provider class. See the phone sign-in docs.",
                id="users.W001",
            ),
        ]
    return []
