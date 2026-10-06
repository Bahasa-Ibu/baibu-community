from django.contrib import admin

from .models import DailyMetric


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    """Read-only: figures are computed by the nightly task or compute_metrics."""

    list_display = ("date", "name", "dimension", "value", "computed_at")
    list_filter = ("name",)
    date_hierarchy = "date"
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
