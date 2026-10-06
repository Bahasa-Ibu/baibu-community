import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TranslationSource(models.Model):
    """The interface strings extracted from the code (a gettext template).

    The newest row is the current template. The file itself lives in private
    storage (``pot_key``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    pot_key = models.CharField(max_length=512)
    # SHA-256 of the extracted entries, so an unchanged extraction is skipped.
    content_hash = models.CharField(max_length=64)
    entry_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        get_latest_by = "created_at"
        verbose_name = _("Source strings")
        verbose_name_plural = _("Source strings")

    def __str__(self) -> str:
        return f"Source strings of {self.created_at:%Y-%m-%d %H:%M}"


class TranslationCatalogue(models.Model):
    """The working copy (draft) of one language's interface translations."""

    language_code = models.CharField(_("Language"), max_length=24, unique=True)
    # The draft .po file in private storage. Replaced on every save.
    draft_key = models.CharField(max_length=512)
    # The template last merged into the draft.
    source = models.ForeignKey(TranslationSource, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["language_code"]
        verbose_name = _("Translation catalogue")
        verbose_name_plural = _("Translation catalogues")
        permissions = [("edit_translations", _("Can edit and publish interface translations"))]

    def __str__(self) -> str:
        return self.language_code


class TranslationPublication(models.Model):
    """One publication of a language's translations: the audit trail.

    Rows are never changed. Publishing again, or restoring an earlier
    version, adds a row; the newest row for a language is what the site uses.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    language_code = models.CharField(_("Language"), max_length=24, db_index=True)
    version = models.PositiveIntegerField()
    po_key = models.CharField(max_length=512)
    mo_key = models.CharField(max_length=512)
    total_count = models.PositiveIntegerField(default=0)
    translated_count = models.PositiveIntegerField(default=0)
    fuzzy_count = models.PositiveIntegerField(default=0)
    restored_from = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", help_text=_("Set for a restore.")
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-published_at"]
        verbose_name = _("Translation publication")
        verbose_name_plural = _("Translation publications")
        constraints = [
            models.UniqueConstraint(fields=["language_code", "version"], name="localization_unique_version"),
        ]

    def __str__(self) -> str:
        return f"{self.language_code} v{self.version}"
