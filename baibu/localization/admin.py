"""Read-only views of the translation records. Translators work at /translations/."""

from django.contrib import admin

from .models import TranslationCatalogue
from .models import TranslationPublication
from .models import TranslationSource


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TranslationPublication)
class TranslationPublicationAdmin(ReadOnlyAdmin):
    list_display = (
        "language_code",
        "version",
        "published_at",
        "published_by",
        "translated_count",
        "fuzzy_count",
        "total_count",
        "restored_from",
    )
    list_filter = ("language_code",)
    search_fields = ("published_by__email",)
    date_hierarchy = "published_at"


@admin.register(TranslationCatalogue)
class TranslationCatalogueAdmin(ReadOnlyAdmin):
    list_display = ("language_code", "updated_at", "updated_by", "source")


@admin.register(TranslationSource)
class TranslationSourceAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "entry_count", "created_by")
