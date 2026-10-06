import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError
from django.db import transaction

from config.email_recipients import resolve_operations_recipients

from .models import AccountDeletionRequest
from .models import User

logger = logging.getLogger(__name__)


def capture_account_deletion_request(  # noqa: PLR0913
    *,
    source: str,
    user: User,
    requester_name: str = "",
    requester_email: str = "",
    request_details: str = "",
    metadata: dict | None = None,
) -> tuple[AccountDeletionRequest, bool]:
    """Record a deletion request and deactivate the account at once.

    Returns the open request and whether it was newly created. A user has at
    most one open request; asking again returns the existing one.
    """
    normalized = {
        "requester_name": " ".join((requester_name or "").split()),
        "requester_email": User.objects.normalize_email_or_none(requester_email) or "",
        "request_details": (request_details or "").strip(),
        "metadata": dict(metadata or {}),
    }
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk)
            if user.is_active:
                user.is_active = False
                user.save(update_fields=["is_active"])
            existing = (
                AccountDeletionRequest.objects.select_for_update()
                .filter(user=user, status__in=AccountDeletionRequest.OPEN_STATUSES)
                .order_by("-requested_at")
                .first()
            )
            if existing is not None:
                return existing, False
            deletion_request = AccountDeletionRequest.objects.create(source=source, user=user, **normalized)
            transaction.on_commit(
                lambda request_id=deletion_request.pk: _notify_operations_safely(request_id),
            )
    except IntegrityError:
        # A concurrent request won the race; return the one that exists.
        User.objects.filter(pk=user.pk, is_active=True).update(is_active=False)
        existing = AccountDeletionRequest.objects.get(user=user, status__in=AccountDeletionRequest.OPEN_STATUSES)
        return existing, False
    return deletion_request, True


def _notify_operations_safely(request_id) -> None:
    try:
        _notify_operations(request_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Account deletion notification failed; request_id=%s error_type=%s",
            request_id,
            type(exc).__name__,
        )


def _notify_operations(request_id) -> None:
    deletion_request = AccountDeletionRequest.objects.only("id", "source", "requested_at").get(pk=request_id)
    recipients = resolve_operations_recipients()
    if not recipients:
        return
    # Personal details stay out of email; staff read them in the admin.
    body = "\n".join(
        [
            "An account deletion request was received.",
            f"Receipt ID: {deletion_request.pk}",
            f"Source: {deletion_request.source}",
            f"Requested at: {deletion_request.requested_at.isoformat()}",
            "",
            "Review the request in the admin. Contact details and request text are left out of this email on purpose.",
        ],
    )
    EmailMessage(
        subject=f"{settings.EMAIL_SUBJECT_PREFIX}Account deletion request {deletion_request.pk}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    ).send(fail_silently=False)
