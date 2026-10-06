import csv
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from . import report
from .forms import RangeForm

PERMISSION = "metrics.view_dailymetric"


def can_view_usage(user) -> bool:
    """Staff with permission to view daily metrics (superusers have every permission)."""
    return bool(user.is_authenticated and user.is_staff and user.has_perm(PERMISSION))


def usage_access_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not can_view_usage(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


@require_GET
@usage_access_required
def usage(request):
    form = RangeForm(request.GET or None, initial=RangeForm.defaults())
    chosen = form.range()
    start, end = chosen["start"], chosen["end"]
    anchor = report.latest_day(timezone.localdate())
    rows = report.daily_rows(start, end)
    context = {
        "form": form,
        "start": start,
        "end": end,
        "anchor": anchor,
        "users_total": report.users_total(anchor) if anchor else None,
        "headlines": report.headlines(anchor) if anchor else [],
        "columns": report.COLUMNS,
        "rows": rows,
        "has_data": any(row["computed"] for row in rows),
        "chart": report.chart(rows, report.COLUMNS_BY_KEY[chosen["chart"]]),
        "breakdowns": report.breakdowns(start, end),
        "consent_day": report.latest_day(end),
        "retention": report.retention(start, end),
        "min_group_size": settings.METRICS_MIN_GROUP_SIZE,
    }
    context["consent"] = report.consent(context["consent_day"])
    return render(request, "metrics/usage.html", context)


@require_GET
@usage_access_required
def export(request):
    form = RangeForm(request.GET or None)
    if form.is_bound and not form.is_valid():
        return HttpResponseBadRequest("Invalid date range.")
    chosen = form.range()
    start, end = chosen["start"], chosen["end"]
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="usage-{start}-{end}.csv"'
    writer = csv.writer(response)
    writer.writerows(report.export_rows(start, end))
    return response
