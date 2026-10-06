from allauth.account.decorators import secure_admin_login
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import AccountDeletionRequest
from .models import ConsentRecord
from .models import User

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


class ConsentRecordInline(admin.TabularInline):
    model = ConsentRecord
    extra = 0
    can_delete = False
    fields = ("scope", "tier", "source", "granted_at", "revoked_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    inlines = (ConsentRecordInline,)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profile"), {"fields": ("name", "city", "country")}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
    list_display = ("email", "name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "name")
    ordering = ("-date_joined",)

    def get_inlines(self, request, obj):
        # Consent history only exists once the user does.
        return self.inlines if obj else ()


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    """Read-only: consent history is append-only."""

    list_display = ("user", "scope", "tier", "source", "granted_at", "revoked_at")
    list_filter = ("scope", "tier", "source")
    search_fields = ("user__email", "user__name")
    readonly_fields = ("id", "user", "tier", "source", "scope", "granted_at", "revoked_at", "metadata", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AccountDeletionRequestAdminForm(forms.ModelForm):
    class Meta:
        model = AccountDeletionRequest
        fields = ("status", "resolution_notes")

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        current = AccountDeletionRequest.objects.get(pk=self.instance.pk)
        if not current.can_transition_to(new_status):
            raise forms.ValidationError(
                _("A request cannot move from %(old)s to %(new)s."),
                params={"old": current.get_status_display(), "new": new_status},
            )
        return new_status


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    form = AccountDeletionRequestAdminForm
    list_display = ("id", "status", "source", "requester_email", "requested_at", "completed_at")
    list_filter = ("status", "source")
    search_fields = ("id", "requester_email", "requester_name", "user__email")
    readonly_fields = (
        "id",
        "source",
        "user",
        "requester_name",
        "requester_email",
        "request_details",
        "metadata",
        "requested_at",
        "updated_at",
        "completed_at",
    )
    fields = (*readonly_fields, "status", "resolution_notes")
    actions = ("mark_completed",)

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if obj.status == AccountDeletionRequest.Status.COMPLETED and obj.completed_at is None:
            obj.completed_at = timezone.now()
            obj.clear_personal_details()
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Mark selected in-progress requests as completed"))
    def mark_completed(self, request, queryset):
        updated = 0
        for deletion_request in queryset.filter(status=AccountDeletionRequest.Status.IN_PROGRESS):
            deletion_request.status = AccountDeletionRequest.Status.COMPLETED
            deletion_request.completed_at = timezone.now()
            deletion_request.clear_personal_details()
            deletion_request.save()
            updated += 1
        self.message_user(request, _("%(count)d request(s) marked completed.") % {"count": updated})
