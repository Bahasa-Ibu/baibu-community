"""Read stored rollups back for the staff usage page and the CSV export."""

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from .definitions import DAILY_METRICS
from .definitions import METRICS
from .definitions import is_suppressed
from .models import DailyMetric

DayValues = dict[tuple[str, str], int]


@dataclass(frozen=True)
class Column:
    """A per-day figure: a metric's total, or one value of a breakdown."""

    key: str
    label: str
    name: str
    dimension: str | None = None  # None: the total over all dimensions
    # How days add up for the headline figures: "sum", or the metric that
    # holds the figure for 7 and 30 days (distinct users), or None (not shown).
    headline: str | None = "sum"
    windows: tuple[str, str] = ("", "")

    def value(self, values: DayValues) -> int | None:
        if self.dimension is not None:
            return values.get((self.name, self.dimension), 0 if values else None)
        if (self.name, "") in values:
            return values[self.name, ""]
        if METRICS[self.name].dimension and values:
            return sum(v for (name, _dimension), v in values.items() if name == self.name)
        return None


COLUMNS = (
    Column("users_new", _("New users"), "users_new"),
    Column(
        "active_users",
        _("Active users"),
        "active_users",
        headline="distinct",
        windows=("active_users_7d", "active_users_30d"),
    ),
    Column("active_users_7d", _("Active, 7 days"), "active_users_7d", headline=None),
    Column("active_users_30d", _("Active, 30 days"), "active_users_30d", headline=None),
    Column("conversations", _("Conversations started"), "conversations"),
    Column("messages_user", _("Messages sent"), "messages_user"),
    Column("messages_assistant", _("Assistant replies"), "messages_assistant"),
    Column("runs_failed", _("Failed reply attempts"), "runs", dimension="failed"),
    Column("reply_time_median_ms", _("Reply time, median (ms)"), "reply_time_median_ms", headline=None),
    Column("reply_time_p90_ms", _("Reply time, 90th percentile (ms)"), "reply_time_p90_ms", headline=None),
    Column("tool_calls", _("Tool calls"), "tool_calls"),
    Column("submissions", _("Submissions"), "submissions"),
)
COLUMNS_BY_KEY = {column.key: column for column in COLUMNS}

BREAKDOWNS = (
    "conversations_by_language",
    "submissions_by_language",
    "submissions_by_status",
    "runs",
    "tool_calls",
)


def display_value(name: str, dimension: str, value: int) -> int | str:
    """The value, or "<N" if it is a small count in a sensitive breakdown."""
    min_size = settings.METRICS_MIN_GROUP_SIZE
    return f"<{min_size}" if is_suppressed(name, dimension, value, min_size) else value


def latest_day(until: date) -> date | None:
    """The last day up to ``until`` that has been computed."""
    return DailyMetric.objects.filter(name="active_users", date__lte=until).aggregate(Max("date"))["date__max"]


def values_by_day(first: date, last: date) -> dict[date, DayValues]:
    days: dict[date, DayValues] = defaultdict(dict)
    rows = DailyMetric.objects.filter(date__gte=first, date__lte=last, name__in=DAILY_METRICS)
    for day, name, dimension, value in rows.values_list("date", "name", "dimension", "value"):
        days[day][name, dimension] = value
    return days


@dataclass
class Headline:
    label: str
    values: list[int | None] = field(default_factory=list)


def headlines(anchor: date) -> list[Headline]:
    """Figures for the last day, 7 days and 30 days up to ``anchor``."""
    days = values_by_day(anchor - timedelta(days=29), anchor)
    last = days.get(anchor, {})
    result = []
    for column in COLUMNS:
        if column.headline == "sum":
            sums = []
            for span in (1, 7, 30):
                window = [days.get(anchor - timedelta(days=offset), {}) for offset in range(span)]
                sums.append(sum(column.value(values) or 0 for values in window))
            result.append(Headline(column.label, sums))
        elif column.headline == "distinct":
            names = (column.name, *column.windows)
            result.append(Headline(column.label, [_plain(last, name) for name in names]))
    return result


def _plain(values: DayValues, name: str) -> int | None:
    return values.get((name, ""))


def users_total(day: date) -> int | None:
    row = DailyMetric.objects.filter(date=day, name="users_total", dimension="").first()
    return row.value if row else None


def daily_rows(first: date, last: date) -> list[dict]:
    """One row per day, newest first; ``computed`` is False for days with no rollups."""
    days = values_by_day(first, last)
    rows = []
    day = last
    while day >= first:
        values = days.get(day, {})
        rows.append(
            {
                "date": day,
                "computed": ("active_users", "") in values,
                "cells": [column.value(values) for column in COLUMNS],
            }
        )
        day -= timedelta(days=1)
    return rows


def chart(rows: list[dict], column: Column) -> dict:
    """Bar geometry for an inline SVG of one column, oldest day on the left."""
    index = COLUMNS.index(column)
    points = [(row["date"], row["cells"][index]) for row in reversed(rows)]
    width, height, gap = 720, 160, 2
    top = max((value or 0 for _day, value in points), default=0)
    step = width / max(len(points), 1)
    bars = []
    for position, (day, value) in enumerate(points):
        bar_height = round((value or 0) / top * height, 1) if top else 0
        bars.append(
            {
                "x": round(position * step + gap / 2, 1),
                "y": round(height - bar_height, 1),
                "width": round(max(step - gap, 1), 1),
                "height": bar_height,
                "date": day,
                "value": value,
            }
        )
    return {"column": column, "bars": bars, "max": top, "width": width, "height": height}


def breakdowns(first: date, last: date) -> list[dict]:
    """Totals over the range for each breakdown, largest first."""
    rows = DailyMetric.objects.filter(date__gte=first, date__lte=last, name__in=BREAKDOWNS).exclude(dimension="")
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for name, dimension, value in rows.values_list("name", "dimension", "value"):
        totals[name][dimension] += value
    result = []
    for name in BREAKDOWNS:
        items = sorted(totals[name].items(), key=lambda item: (-item[1], item[0]))
        result.append(
            {
                "metric": METRICS[name],
                "rows": [(dimension, display_value(name, dimension, value)) for dimension, value in items],
            }
        )
    return result


def consent(day: date | None) -> list[tuple[str, str, int | str]]:
    """Users per consent scope and tier at the end of ``day``."""
    if day is None:
        return []
    rows = DailyMetric.objects.filter(date=day, name="consent").values_list("dimension", "value")
    result = []
    for dimension, value in sorted(rows):
        scope, _sep, tier = dimension.partition(":")
        result.append((scope, tier, display_value("consent", dimension, value)))
    return result


def retention(first: date, last: date) -> dict:
    """Weekly cohorts that start between ``first`` and ``last``, newest first."""
    weeks = list(range(1, settings.METRICS_RETENTION_WEEKS + 1))
    rows = DailyMetric.objects.filter(date__gte=first, date__lte=last, name__startswith="retention_")
    cohorts: dict[date, dict[str, int]] = defaultdict(dict)
    for day, name, dimension, value in rows.values_list("date", "name", "dimension", "value"):
        cohorts[day][dimension if name == "retention_active" else "size"] = value
    result = []
    for day in sorted(cohorts, reverse=True):
        size = cohorts[day].get("size")
        if not size:
            continue
        cells = []
        for week in weeks:
            active = cohorts[day].get(str(week))
            cells.append(None if active is None else {"value": active, "percent": round(100 * active / size)})
        result.append({"week": day, "size": size, "cells": cells})
    return {"weeks": weeks, "cohorts": result}


def export_rows(first: date, last: date):
    """CSV rows (header first) for every stored value dated in the range."""
    yield ["date", "name", "dimension", "value"]
    rows = DailyMetric.objects.filter(date__gte=first, date__lte=last).order_by("date", "name", "dimension")
    for day, name, dimension, value in rows.values_list("date", "name", "dimension", "value"):
        yield [day.isoformat(), name, dimension, display_value(name, dimension, value)]
