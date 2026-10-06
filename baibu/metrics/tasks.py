from celery import shared_task

from . import rollups


@shared_task(ignore_result=True)
def compute_daily_metrics() -> dict:
    """Nightly: compute yesterday's rollups, and any earlier days the worker missed."""
    first, last = rollups.days_to_catch_up()
    days = rollups.store_range(first, last)
    return {"first": first.isoformat(), "last": last.isoformat(), "days": days}
