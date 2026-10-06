import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from baibu.users.models import ConsentRecord


class Submission(models.Model):
    """A piece of writing contributed by a user.

    The full text lives in private file storage (``raw_key``, then
    ``clean_key`` once cleaned); the database keeps an excerpt of the cleaned
    text, counts and the cleaning outcome.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        VERIFIED = "verified", _("Verified")
        NEEDS_REVIEW = "needs_review", _("Needs review")
        REJECTED = "rejected", _("Rejected")
        ISSUE = "issue", _("Issue")

    # Cleaning moves a pending submission on; staff decide the rest. "Clean
    # again" sends a submission back to pending.
    TRANSITIONS = {
        Status.PENDING: {Status.VERIFIED, Status.NEEDS_REVIEW, Status.ISSUE},
        Status.NEEDS_REVIEW: {Status.VERIFIED, Status.REJECTED, Status.PENDING},
        Status.ISSUE: {Status.PENDING, Status.REJECTED},
        Status.VERIFIED: {Status.REJECTED, Status.PENDING},
        Status.REJECTED: {Status.PENDING},
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    language_code = models.CharField(_("Language"), max_length=24)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)

    # Consent in force when the text was submitted.
    consent_tier = models.CharField(max_length=32, choices=ConsentRecord.Tier.choices)
    consent_record = models.ForeignKey(
        ConsentRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    # Storage keys (see baibu.core.storage), not URLs.
    raw_key = models.CharField(max_length=512)
    clean_key = models.CharField(max_length=512, blank=True)
    # SHA-256 of the normalised raw text, to refuse duplicates.
    content_hash = models.CharField(max_length=64, unique=True)
    word_count = models.PositiveIntegerField(default=0)
    character_count = models.PositiveIntegerField(default=0)
    # Start of the cleaned text; empty until cleaning has run.
    excerpt = models.TextField(blank=True)

    # Cleaning outcome.
    cleaner = models.CharField(max_length=128, blank=True, help_text=_("Cleaner (and model) that produced it."))
    redaction_count = models.PositiveIntegerField(null=True, blank=True)
    toxicity_detected = models.BooleanField(null=True, blank=True)
    quality_score = models.PositiveSmallIntegerField(null=True, blank=True, help_text=_("0 to 100."))
    detected_language = models.CharField(max_length=24, blank=True)
    flags = models.JSONField(default=list, blank=True)
    decision_reason = models.CharField(max_length=512, blank=True)
    cleaned_at = models.DateTimeField(null=True, blank=True)

    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Submission")
        verbose_name_plural = _("Submissions")

    def __str__(self) -> str:
        return f"Submission {self.pk}"

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.TRANSITIONS.get(self.status, set())
