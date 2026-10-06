"""The metrics the platform counts, with how each one adds up over days.

The exact definitions are in ``docs/developer/metrics.md``; keep the two in
step. Every value is an integer count (or a whole number of milliseconds).
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

# How a metric combines over several days.
SUM = "sum"  # events: add the daily values
DISTINCT = "distinct"  # distinct users: days cannot be added; read the value on the last day
SNAPSHOT = "snapshot"  # a state at the end of the day: read the value on the last day
DURATION = "duration"  # a median or percentile in milliseconds: shown per day only
COHORT = "cohort"  # retention: dated by the cohort week, not by a day of activity


@dataclass(frozen=True)
class Metric:
    name: str
    label: str
    kind: str
    # What the dimension holds for a breakdown; empty for a plain total.
    dimension: str = ""
    # Breakdowns that could point at a few people (by language or consent
    # tier) show small values as "fewer than METRICS_MIN_GROUP_SIZE".
    suppress_small: bool = False


METRICS: dict[str, Metric] = {
    metric.name: metric
    for metric in (
        Metric("users_new", _("New users"), SUM),
        Metric("users_total", _("Users"), SNAPSHOT),
        Metric("active_users", _("Active users"), DISTINCT),
        Metric("active_users_7d", _("Active users, 7 days"), DISTINCT),
        Metric("active_users_30d", _("Active users, 30 days"), DISTINCT),
        Metric("chat_users", _("Users who chatted"), DISTINCT),
        Metric("contributors", _("Users who contributed"), DISTINCT),
        Metric("conversations", _("Conversations started"), SUM),
        Metric("conversations_by_language", _("Conversations by language"), SUM, _("Language"), suppress_small=True),
        Metric("messages_user", _("Messages sent"), SUM),
        Metric("messages_assistant", _("Assistant replies"), SUM),
        Metric("runs", _("Reply attempts"), SUM, _("Status")),
        Metric("reply_time_median_ms", _("Reply time, median (ms)"), DURATION),
        Metric("reply_time_p90_ms", _("Reply time, 90th percentile (ms)"), DURATION),
        Metric("tool_calls", _("Tool calls"), SUM, _("Status")),
        Metric("submissions", _("Submissions"), SUM),
        Metric("submissions_by_status", _("Submissions by status"), SUM, _("Status")),
        Metric("submissions_by_language", _("Submissions by language"), SUM, _("Language"), suppress_small=True),
        Metric("consent", _("Current consent"), SNAPSHOT, _("Scope and tier"), suppress_small=True),
        Metric("retention_cohort_size", _("Cohort size"), COHORT),
        Metric("retention_active", _("Cohort users active"), COHORT, _("Weeks after joining")),
    )
}

# Metrics stored under the day they describe (everything except retention).
DAILY_METRICS = tuple(name for name, metric in METRICS.items() if metric.kind != COHORT)
RETENTION_METRICS = tuple(name for name, metric in METRICS.items() if metric.kind == COHORT)


def is_suppressed(name: str, dimension: str, value: int, min_group_size: int) -> bool:
    """True if ``value`` is a small, non-zero count in a sensitive breakdown."""
    metric = METRICS.get(name)
    return bool(metric and metric.suppress_small and dimension and 0 < value < min_group_size)
