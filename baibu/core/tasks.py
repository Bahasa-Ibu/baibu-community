from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

HEARTBEAT_CACHE_KEY = "core:worker-heartbeat"


@shared_task(ignore_result=True)
def heartbeat() -> str:
    """Record that a worker executed a task. Celery beat schedules this."""
    now = timezone.now().isoformat()
    cache.set(HEARTBEAT_CACHE_KEY, now, timeout=None)
    return now
