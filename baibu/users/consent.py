"""Reading and recording consent decisions.

Feature code asks ``consent_state`` whether a user has agreed to a use of
their data, and records changes with ``record_consent``. Never update or
delete ConsentRecord rows directly.
"""

from dataclasses import dataclass
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import ConsentRecord
from .models import User

# Higher tiers include the uses allowed by lower ones.
TIER_RANK = {
    ConsentRecord.Tier.NONE: 0,
    ConsentRecord.Tier.EVAL_ONLY: 1,
    ConsentRecord.Tier.TRAINING_ELIGIBLE: 2,
}


@dataclass(frozen=True)
class ConsentState:
    latest_record: ConsentRecord | None

    @property
    def tier(self) -> str:
        record = self.latest_record
        if record is None or record.revoked_at is not None:
            return ConsentRecord.Tier.NONE
        return record.tier

    def allows(self, tier: str) -> bool:
        return TIER_RANK[self.tier] >= TIER_RANK[tier]


def default_scope() -> str:
    return settings.CONSENT_DEFAULT_SCOPE


def latest_consent(*, user: User, scope: str | None = None) -> ConsentRecord | None:
    return user.consent_records.filter(scope=scope or default_scope()).order_by("-granted_at", "-created_at").first()


def consent_state(*, user: User, scope: str | None = None) -> ConsentState:
    return ConsentState(latest_record=latest_consent(user=user, scope=scope))


def record_consent(
    *,
    user: User,
    tier: str,
    source: str,
    scope: str | None = None,
    metadata: dict | None = None,
) -> ConsentRecord:
    """Record a new consent decision and revoke the one it replaces."""
    scope = scope or default_scope()
    now = timezone.now()
    with transaction.atomic():
        ConsentRecord.objects.select_for_update().filter(
            user=user,
            scope=scope,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        return ConsentRecord.objects.create(
            user=user,
            tier=tier,
            source=source,
            scope=scope,
            granted_at=now,
            metadata=dict(metadata or {}),
        )


def consent_required(tier: str, *, scope: str | None = None, redirect_to: str = "users:consent"):
    """View decorator: send users without at least ``tier`` consent to the consent page."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(settings.LOGIN_URL)
            if not consent_state(user=request.user, scope=scope).allows(tier):
                messages.info(request, _("Please review how your contributions may be used before continuing."))
                return redirect(redirect_to)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
