from django.contrib import admin
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import ChatFlag
from .models import Conversation
from .models import ConversationEvent
from .models import Message
from .models import ModelVariant
from .models import Prompt
from .models import Run
from .models import ToolInvocation


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class MessageInline(ReadOnlyInline):
    model = Message
    fields = ("created_at", "role", "content")
    readonly_fields = fields


class RunInline(ReadOnlyInline):
    model = Run
    fields = ("created_at", "status", "attempt", "model_name", "prompt_version", "latency_ms", "error")
    readonly_fields = fields


class ToolInvocationInline(ReadOnlyInline):
    model = ToolInvocation
    fields = ("created_at", "tool_name", "provider", "status", "arguments", "result_count", "error", "latency_ms")
    readonly_fields = fields


class EventInline(ReadOnlyInline):
    model = ConversationEvent
    fields = ("created_at", "type", "payload")
    readonly_fields = fields


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "language_code", "consent_tier", "last_activity_at")
    list_filter = ("consent_tier", "language_code")
    search_fields = ("id", "user__email", "title")
    date_hierarchy = "last_activity_at"
    readonly_fields = ("id", "user", "title", "language_code", "consent_tier", "created_at", "last_activity_at")
    inlines = (MessageInline, RunInline, EventInline)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD"} and super().has_change_permission(request, obj)


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "status", "attempt", "model_name", "latency_ms", "created_at")
    list_filter = ("status", "model_name")
    date_hierarchy = "created_at"
    readonly_fields = [field.name for field in Run._meta.fields]
    inlines = (ToolInvocationInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD"} and super().has_change_permission(request, obj)


@admin.register(ModelVariant)
class ModelVariantAdmin(admin.ModelAdmin):
    list_display = ("name", "model", "api_base", "is_default")
    fields = ("name", "model", "api_base", "api_key_env", "parameters", "is_default")

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if obj.is_default:
                ModelVariant.objects.exclude(pk=obj.pk).update(is_default=False)
            super().save_model(request, obj, form, change)


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    """Adding a prompt creates the next version; existing versions cannot be edited."""

    list_display = ("name", "version", "active", "notes", "created_by", "created_at")
    list_filter = ("name", "active")
    actions = ("activate",)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("name", "body", "notes", "active")
        return ("name", "version", "body", "notes", "active", "created_by", "created_at")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("name", "version", "body", "notes", "created_by", "created_at")

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if not change:
                obj.created_by = request.user
            if obj.active:
                Prompt.objects.filter(name=obj.name, active=True).exclude(pk=obj.pk).update(active=False)
            super().save_model(request, obj, form, change)

    @admin.action(description=_("Make the selected version active"))
    def activate(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, _("Select exactly one version."), level="warning")
            return
        prompt = queryset.get()
        with transaction.atomic():
            Prompt.objects.filter(name=prompt.name, active=True).update(active=False)
            Prompt.objects.filter(pk=prompt.pk).update(active=True)
        self.message_user(request, _("%(prompt)s is now active.") % {"prompt": prompt})


@admin.register(ChatFlag)
class ChatFlagAdmin(admin.ModelAdmin):
    list_display = ("__str__", "conversation", "created_at", "decided_by")
    list_filter = ("status", "reason")
    readonly_fields = [field.name for field in ChatFlag._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD"} and super().has_change_permission(request, obj)
