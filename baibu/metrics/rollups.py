"""Compute the daily rollups from the platform's own tables.

Days are calendar days in the platform time zone (``TIME_ZONE``). Computing
a day again replaces what was stored for it, so every function here can be
run as often as needed. Only counts are stored.
"""

from collections import Counter
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Aggregate
from django.db.models import Count
from django.db.models import Exists
from django.db.models import F
from django.db.models import FloatField
from django.db.models import Func
from django.db.models import Max
from django.db.models import OuterRef
from django.db.models import QuerySet
from django.utils import timezone

from baibu.chat.models import Conversation
from baibu.chat.models import Message
from baibu.chat.models import Run
from baibu.chat.models import ToolInvocation
from baibu.submissions.models import Submission
from baibu.users.models import ConsentRecord

from .definitions import DAILY_METRICS
from .models import DailyMetric

User = get_user_model()

Key = tuple[str, str]  # (name, dimension)


class PercentileCont(Aggregate):
    """PostgreSQL's continuous percentile (interpolated), e.g. 0.5 for the median."""

    function = "percentile_cont"
    template = "%(function)s(%(fraction)s) WITHIN GROUP (ORDER BY %(expressions)s)"
    output_field = FloatField()

    def __init__(self, expression, fraction: float, **extra):
        super().__init__(expression, fraction=float(fraction), **extra)


class EpochSeconds(Func):
    template = "EXTRACT(EPOCH FROM %(expressions)s)"
    output_field = FloatField()


def day_start(day: date) -> datetime:
    """Midnight at the start of ``day`` in the platform time zone."""
    return datetime.combine(day, time.min, tzinfo=timezone.get_default_timezone())


def day_bounds(first: date, last: date | None = None) -> dict:
    """Lookup values for ``created_at`` from the start of ``first`` to the end of ``last``."""
    return {"gte": day_start(first), "lt": day_start((last or first) + timedelta(days=1))}


def week_start(day: date) -> date:
    """The Monday of the week that contains ``day``."""
    return day - timedelta(days=day.weekday())


def yesterday() -> date:
    return timezone.localdate() - timedelta(days=1)


def _between(field: str, first: date, last: date | None = None) -> dict:
    bounds = day_bounds(first, last)
    return {f"{field}__gte": bounds["gte"], f"{field}__lt": bounds["lt"]}


def active_users(first: date, last: date | None = None, *, users: QuerySet | None = None) -> QuerySet:
    """Users who sent a chat message or made a submission between ``first`` and ``last``."""
    chatted = Message.objects.filter(
        conversation__user=OuterRef("pk"), role=Message.Role.USER, **_between("created_at", first, last)
    )
    contributed = Submission.objects.filter(user=OuterRef("pk"), **_between("created_at", first, last))
    users = User.objects.all() if users is None else users
    return users.filter(Exists(chatted) | Exists(contributed))


def _counts_by(queryset: QuerySet, field: str) -> dict[str, int]:
    rows = queryset.order_by().values(field).annotate(n=Count("pk")).values_list(field, "n")
    # A blank value (for example a conversation without a language) is "unknown",
    # because an empty dimension means a plain total.
    return {str(key) if key else "unknown": n for key, n in rows}


def _consent_at(end: datetime) -> Counter:
    """Each user's tier per scope at ``end``, counted as ``scope:tier``."""
    latest = (
        ConsentRecord.objects.filter(granted_at__lt=end)
        .order_by("user_id", "scope", "-granted_at", "-created_at")
        .distinct("user_id", "scope")
        .values_list("scope", "tier", "revoked_at")
    )
    counts: Counter = Counter()
    for scope, tier, revoked_at in latest:
        current = ConsentRecord.Tier.NONE if revoked_at is not None and revoked_at < end else tier
        counts[f"{scope}:{current}"] += 1
    return counts


def compute_day(day: date) -> dict[Key, int]:
    """Every daily metric for ``day``. Breakdowns leave out zero values."""
    created = _between("created_at", day)
    end = day_bounds(day)["lt"]
    values: dict[Key, int] = {
        ("users_new", ""): User.objects.filter(**_between("date_joined", day)).count(),
        ("users_total", ""): User.objects.filter(date_joined__lt=end).count(),
        ("active_users", ""): active_users(day).count(),
        ("active_users_7d", ""): active_users(day - timedelta(days=6), day).count(),
        ("active_users_30d", ""): active_users(day - timedelta(days=29), day).count(),
        ("chat_users", ""): Message.objects.filter(role=Message.Role.USER, **created)
        .values("conversation__user_id")
        .distinct()
        .count(),
        ("contributors", ""): Submission.objects.filter(**created).values("user_id").distinct().count(),
        ("messages_user", ""): Message.objects.filter(role=Message.Role.USER, **created).count(),
        ("messages_assistant", ""): Message.objects.filter(role=Message.Role.ASSISTANT, **created).count(),
    }

    conversations = Conversation.objects.filter(**created)
    values["conversations", ""] = conversations.count()
    breakdowns = {
        "conversations_by_language": _counts_by(conversations, "language_code"),
        "runs": _counts_by(Run.objects.filter(**created), "status"),
        "tool_calls": _counts_by(ToolInvocation.objects.filter(**created), "status"),
        "submissions_by_status": _counts_by(Submission.objects.filter(**created), "status"),
        "submissions_by_language": _counts_by(Submission.objects.filter(**created), "language_code"),
        "consent": _consent_at(end),
    }
    values["submissions", ""] = sum(breakdowns["submissions_by_status"].values())
    for name, counts in breakdowns.items():
        values.update({(name, dimension): n for dimension, n in counts.items() if n})

    reply_seconds = EpochSeconds(F("completed_at") - F("created_at"))
    times = Run.objects.filter(status=Run.Status.COMPLETED, completed_at__isnull=False, **created).aggregate(
        median=PercentileCont(reply_seconds, 0.5), p90=PercentileCont(reply_seconds, 0.9)
    )
    if times["median"] is not None:
        values["reply_time_median_ms", ""] = round(times["median"] * 1000)
        values["reply_time_p90_ms", ""] = round(times["p90"] * 1000)
    return values


def compute_retention(day: date) -> dict[tuple[date, str, str], int | None]:
    """Retention cells that activity on ``day`` can change.

    A cohort is the users who joined in one week (Monday to Sunday). For the
    week that contains ``day`` and each of the ``METRICS_RETENTION_WEEKS``
    cohorts before it, this returns the cohort's size and how many of its
    users were active in that week. ``None`` marks cells of an empty cohort.
    """
    activity_week = week_start(day)
    activity_end = activity_week + timedelta(days=6)
    cells: dict[tuple[date, str, str], int | None] = {}
    for weeks_after in range(settings.METRICS_RETENTION_WEEKS + 1):
        cohort_week = activity_week - timedelta(weeks=weeks_after)
        cohort = User.objects.filter(**_between("date_joined", cohort_week, cohort_week + timedelta(days=6)))
        size = cohort.count()
        cells[cohort_week, "retention_cohort_size", ""] = size or None
        if weeks_after:
            active = active_users(activity_week, activity_end, users=cohort).count() if size else None
            cells[cohort_week, "retention_active", str(weeks_after)] = active
    return cells


@transaction.atomic
def store_day(day: date) -> int:
    """Compute and store ``day``, replacing earlier values. Returns the rows stored."""
    values = compute_day(day)
    DailyMetric.objects.filter(date=day, name__in=DAILY_METRICS).delete()
    DailyMetric.objects.bulk_create(
        DailyMetric(date=day, name=name, dimension=dimension, value=value)
        for (name, dimension), value in values.items()
    )
    stored = len(values)
    for (cohort_week, name, dimension), value in compute_retention(day).items():
        if value is None:
            DailyMetric.objects.filter(date=cohort_week, name=name, dimension=dimension).delete()
        else:
            DailyMetric.objects.update_or_create(
                date=cohort_week, name=name, dimension=dimension, defaults={"value": value}
            )
            stored += 1
    return stored


def store_range(first: date, last: date) -> int:
    """Compute and store every day from ``first`` to ``last``. Returns the number of days."""
    day = first
    while day <= last:
        store_day(day)
        day += timedelta(days=1)
    return (last - first).days + 1 if last >= first else 0


def days_to_catch_up(today: date | None = None) -> tuple[date, date]:
    """The days the nightly task computes: from the day after the last stored day to yesterday.

    Always includes yesterday, and goes back at most
    ``METRICS_CATCH_UP_DAYS`` days, so a stopped worker fills the gap.
    """
    last = (today or timezone.localdate()) - timedelta(days=1)
    earliest = last - timedelta(days=max(settings.METRICS_CATCH_UP_DAYS, 1) - 1)
    latest_stored = DailyMetric.objects.filter(name="active_users", date__lte=last).aggregate(Max("date"))["date__max"]
    first = last if latest_stored is None else max(earliest, min(latest_stored + timedelta(days=1), last))
    return first, last
