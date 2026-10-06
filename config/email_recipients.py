"""Who receives operational emails (for example, new account deletion requests).

Active users in the ``operations-email`` group receive them. If the group is
empty or missing, the addresses in ``settings.ADMINS`` are used instead.
"""

from django.conf import settings
from django.contrib.auth import get_user_model

OPERATIONS_EMAIL_GROUP_NAME = "operations-email"


def resolve_operations_recipients() -> list[str]:
    user_model = get_user_model()
    candidates = list(
        user_model.objects.filter(groups__name=OPERATIONS_EMAIL_GROUP_NAME, is_active=True)
        .exclude(email__isnull=True)
        .exclude(email="")
        .order_by("email")
        .values_list("email", flat=True),
    )
    if not candidates:
        candidates = [email for _, email in getattr(settings, "ADMINS", [])]
    return _dedupe(candidates)


def _dedupe(candidates: list[str]) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    for email in candidates:
        normalized = email.strip()
        if normalized and normalized.lower() not in seen:
            recipients.append(normalized)
            seen.add(normalized.lower())
    return recipients
