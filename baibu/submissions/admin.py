from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from baibu.core import storage

from .models import Submission
from .services import requeue
from .services import review


def _stored_text(key: str) -> str:
    payload = storage.read_json(key) if key else None
    if payload is None:
        return "—"
    return format_html('<div style="white-space: pre-wrap; max-width: 60rem">{}</div>', payload.get("text", ""))


def _move(modeladmin, request, queryset, status):
    moved = sum(review(submission, status, reviewer=request.user) for submission in queryset)
    skipped = queryset.count() - moved
    modeladmin.message_user(
        request, ngettext("%(n)d submission updated.", "%(n)d submissions updated.", moved) % {"n": moved}
    )
    if skipped:
        modeladmin.message_user(
            request,
            ngettext(
                "%(n)d submission skipped: that change is not allowed from its status.",
                "%(n)d submissions skipped: that change is not allowed from their status.",
                skipped,
            )
            % {"n": skipped},
            level=messages.WARNING,
        )


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "language_code", "status", "word_count", "consent_tier", "created_at")
    list_filter = ("status", "language_code", "consent_tier", "toxicity_detected")
    search_fields = ("id", "user__email", "excerpt")
    date_hierarchy = "created_at"
    actions = ("mark_verified", "mark_rejected", "clean_again")
    fieldsets = (
        (None, {"fields": ("id", "user", "language_code", "status", "decision_reason", "staff_notes")}),
        (_("Review"), {"fields": ("reviewed_by", "reviewed_at")}),
        (_("Text"), {"fields": ("cleaned_text", "raw_text", "word_count", "character_count")}),
        (
            _("Cleaning"),
            {
                "fields": (
                    "cleaner",
                    "cleaned_at",
                    "redaction_count",
                    "toxicity_detected",
                    "quality_score",
                    "detected_language",
                    "flags",
                )
            },
        ),
        (_("Consent and storage"), {"fields": ("consent_tier", "consent_record", "raw_key", "clean_key")}),
        (_("Dates"), {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = tuple(f for _name, options in fieldsets for f in options["fields"] if f not in {"staff_notes"})

    def has_add_permission(self, request):
        return False

    @admin.display(description=_("Cleaned text"))
    def cleaned_text(self, obj):
        return _stored_text(obj.clean_key)

    @admin.display(description=_("Text as submitted"))
    def raw_text(self, obj):
        return _stored_text(obj.raw_key)

    @admin.action(description=_("Mark as verified"))
    def mark_verified(self, request, queryset):
        _move(self, request, queryset, Submission.Status.VERIFIED)

    @admin.action(description=_("Mark as rejected"))
    def mark_rejected(self, request, queryset):
        _move(self, request, queryset, Submission.Status.REJECTED)

    @admin.action(description=_("Clean again"))
    def clean_again(self, request, queryset):
        queued = sum(requeue(submission) for submission in queryset)
        self.message_user(
            request, ngettext("%(n)d submission queued.", "%(n)d submissions queued.", queued) % {"n": queued}
        )
