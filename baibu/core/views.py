import logging
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .tasks import HEARTBEAT_CACHE_KEY

logger = logging.getLogger(__name__)


def _check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check: database unavailable")
        return False
    return True


def _check_cache() -> bool:
    try:
        cache.set("core:health-probe", "ok", timeout=10)
        return cache.get("core:health-probe") == "ok"
    except Exception:
        logger.exception("Health check: cache unavailable")
        return False


def _worker_status() -> str:
    """``ok`` if a worker ran the heartbeat task recently, else ``stale`` or ``unknown``."""
    value = cache.get(HEARTBEAT_CACHE_KEY)
    if not value:
        return "unknown"
    try:
        last_beat = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return "unknown"
    age = (timezone.now() - last_beat).total_seconds()
    return "ok" if age <= settings.WORKER_HEARTBEAT_STALE_SECONDS else "stale"


@never_cache
def health(request: HttpRequest) -> JsonResponse:
    """Liveness for operators and container health checks.

    Returns 503 when the database or cache is down. The worker status is
    reported but does not fail the check, so the web container is not
    restarted because a worker is down.
    """
    database_ok = _check_database()
    cache_ok = _check_cache()
    healthy = database_ok and cache_ok
    return JsonResponse(
        {
            "status": "ok" if healthy else "error",
            "database": "ok" if database_ok else "error",
            "cache": "ok" if cache_ok else "error",
            "worker": _worker_status(),
        },
        status=200 if healthy else 503,
    )
