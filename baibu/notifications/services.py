"""Sending and reading notifications.

Feature code calls :func:`notify`; it never fails the caller's work. Use a
kind registered in :mod:`.kinds` so the text is shown in the reader's
language; ``title`` and ``body`` are a fallback for unregistered kinds.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)


def notify(  # noqa: PLR0913
    user, *, kind: str, params: dict | None = None, title: str = "", body: str = "", link: str = ""
) -> Notification | None:
    if not settings.NOTIFICATIONS_ENABLED or not user.is_active:
        return None
    if link and not link.startswith("/"):
        # Only links inside the platform.
        link = ""
    try:
        return Notification.objects.create(
            user=user,
            kind=kind[:64],
            params=params or {},
            title=str(title)[:200],
            body=str(body),
            link=link[:500],
        )
    except Exception:
        logger.exception("Could not create a %s notification", kind)
        return None


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_read(notification: Notification) -> None:
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])


def mark_all_read(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())


def delete_old(now=None) -> int:
    """Delete read notifications older than the retention period."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.NOTIFICATIONS_RETENTION_DAYS)
    deleted, _ = Notification.objects.filter(read_at__isnull=False, created_at__lt=cutoff).delete()
    return deleted
