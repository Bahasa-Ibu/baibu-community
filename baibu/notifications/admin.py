from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "kind", "created_at", "read_at")
    list_filter = ("kind",)
    search_fields = ("user__email", "title")
    readonly_fields = ("id", "user", "kind", "params", "title", "body", "link", "created_at", "read_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD"} and super().has_change_permission(request, obj)
