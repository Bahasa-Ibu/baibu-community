import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ImmutableRecordError(Exception):
    """Raised when code tries to change a record that must never change."""


class UserManager(BaseUserManager):
    """Manager for a user model that signs in by email and has no username."""

    use_in_migrations = True

    def normalize_email_or_none(self, email: str | None) -> str | None:
        email = (email or "").strip()
        if not email:
            return None
        return self.normalize_email(email)

    def _create_user(self, email, password, **extra_fields):
        email = self.normalize_email_or_none(email)
        if not email:
            msg = "The email address must be set."
            raise ValueError(msg)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            msg = "Superuser must have is_staff=True."
            raise ValueError(msg)
        if extra_fields.get("is_superuser") is not True:
            msg = "Superuser must have is_superuser=True."
            raise ValueError(msg)
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """A person using the platform: contributor, staff member or both."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    username = None  # type: ignore[assignment]
    email = models.EmailField(_("Email address"), unique=True, null=True, blank=True)
    # One name field: first and last names do not fit naming patterns everywhere.
    name = models.CharField(_("Name"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    city = models.CharField(_("City"), max_length=128, blank=True)
    country = models.CharField(_("Country"), max_length=128, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        original_email = self.email
        self.email = User.objects.normalize_email_or_none(self.email)
        if original_email != self.email and (update_fields := kwargs.get("update_fields")):
            if "email" not in update_fields:
                kwargs["update_fields"] = [*update_fields, "email"]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("users:account")

    def display_identifier(self) -> str:
        return self.name or self.email or str(self.pk)

    def __str__(self) -> str:
        return self.display_identifier()


class ConsentRecord(models.Model):
    """One consent decision by a user. Rows are never edited or deleted.

    A new decision adds a row and marks the previous one revoked, so the full
    history of what a person agreed to, and when, is kept.
    """

    class Tier(models.TextChoices):
        NONE = "none", _("No data use")
        EVAL_ONLY = "eval_only", _("Evaluation only")
        TRAINING_ELIGIBLE = "training_eligible", _("Training eligible")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consent_records",
    )
    tier = models.CharField(max_length=32, choices=Tier.choices)
    source = models.CharField(max_length=64, help_text=_("Where the decision was made, e.g. account_settings."))
    scope = models.CharField(max_length=64, help_text=_("What the decision covers, e.g. platform or chat."))
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-granted_at", "-created_at"]
        indexes = [models.Index(fields=["user", "scope", "-granted_at"])]
        verbose_name = _("Consent record")
        verbose_name_plural = _("Consent records")

    def __str__(self) -> str:
        return f"{self.user.display_identifier()} ({self.scope}: {self.tier})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            msg = "Consent records are append-only; record a new decision with record_consent()."
            raise ImmutableRecordError(msg)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        msg = "Consent records are append-only and cannot be deleted one by one."
        raise ImmutableRecordError(msg)


class AccountDeletionRequest(models.Model):
    """A request by a user to delete their account and data.

    Capturing a request deactivates the account straight away; staff then
    work the request through the statuses below.
    """

    class Source(models.TextChoices):
        IN_APP = "in_app", _("In app")
        WEB = "web", _("Web")

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Submitted")
        APPROVED = "approved", _("Approved")
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")
        REJECTED = "rejected", _("Rejected")
        FAILED = "failed", _("Failed")

    OPEN_STATUSES = (Status.SUBMITTED, Status.APPROVED, Status.IN_PROGRESS, Status.FAILED)
    # Which status may follow which. Completed and rejected are final.
    ALLOWED_TRANSITIONS = {
        Status.SUBMITTED: {Status.APPROVED, Status.REJECTED},
        Status.APPROVED: {Status.IN_PROGRESS, Status.REJECTED},
        Status.IN_PROGRESS: {Status.COMPLETED, Status.FAILED},
        Status.FAILED: {Status.IN_PROGRESS, Status.REJECTED},
        Status.COMPLETED: set(),
        Status.REJECTED: set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    source = models.CharField(max_length=32, choices=Source.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.SUBMITTED)
    # Kept as a receipt after the account itself is deleted.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_deletion_requests",
    )
    requester_name = models.CharField(max_length=255, blank=True)
    requester_email = models.EmailField(blank=True)
    request_details = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status__in=["submitted", "approved", "in_progress", "failed"]),
                name="users_one_open_account_deletion_request_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "requested_at"]),
            models.Index(fields=["source", "requested_at"]),
        ]
        verbose_name = _("Account deletion request")
        verbose_name_plural = _("Account deletion requests")

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"

    def can_transition_to(self, new_status: str) -> bool:
        return new_status == self.status or new_status in self.ALLOWED_TRANSITIONS[self.status]

    def clear_personal_details(self) -> None:
        """Blank the requester's details once the request is finished; the receipt stays."""
        self.requester_name = ""
        self.requester_email = ""
        self.request_details = ""
