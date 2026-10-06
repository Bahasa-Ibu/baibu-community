import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from baibu.users.models import ConsentRecord
from baibu.users.models import ImmutableRecordError


class ModelVariant(models.Model):
    """A language model the assistant can use, reached through LiteLLM.

    ``model`` is any model name LiteLLM accepts. The special name ``mock``
    answers locally without a network call, for development and tests.
    """

    name = models.CharField(max_length=128, unique=True)
    model = models.CharField(max_length=255, help_text=_("LiteLLM model name, or 'mock'."))
    api_base = models.CharField(max_length=512, blank=True, help_text=_("Endpoint URL, if the model needs one."))
    api_key_env = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("Name of the environment variable that holds the API key. Keys are never stored here."),
    )
    parameters = models.JSONField(
        default=dict, blank=True, help_text=_('Extra parameters for every call, e.g. {"temperature": 0.7}.')
    )
    is_default = models.BooleanField(default=False, help_text=_("Used for new replies. Only one can be the default."))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=models.Q(is_default=True), name="chat_one_default_model"
            ),
        ]
        verbose_name = _("Model variant")
        verbose_name_plural = _("Model variants")

    def __str__(self) -> str:
        return self.name

    def validate_constraints(self, exclude=None):
        # The admin moves the default flag when saving, so do not refuse a second default here.
        super().validate_constraints(exclude={*(exclude or ()), "is_default"})


class Prompt(models.Model):
    """One version of a named prompt. Versions are never edited once saved."""

    name = models.CharField(max_length=64, default="system")
    version = models.PositiveIntegerField(editable=False)
    body = models.TextField(
        help_text=_("A Django template. Available: platform, user_name, language_code, language_name.")
    )
    active = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["name", "version"], name="chat_prompt_name_version"),
            models.UniqueConstraint(
                fields=["name"], condition=models.Q(active=True), name="chat_one_active_prompt_per_name"
            ),
        ]
        verbose_name = _("Prompt")
        verbose_name_plural = _("Prompts")

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            latest = Prompt.objects.filter(name=self.name).aggregate(models.Max("version"))["version__max"]
            self.version = (latest or 0) + 1
        elif Prompt.objects.filter(pk=self.pk).exclude(body=self.body).exists():
            msg = "Prompt versions cannot be edited; save a new version instead."
            raise ImmutableRecordError(msg)
        super().save(*args, **kwargs)

    def validate_constraints(self, exclude=None):
        # The admin moves the active flag when saving, so do not refuse a second active version here.
        super().validate_constraints(exclude={*(exclude or ()), "active"})


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=120, blank=True)
    language_code = models.CharField(max_length=24, blank=True)
    # Consent under the chat scope when the conversation started.
    consent_tier = models.CharField(max_length=32, choices=ConsentRecord.Tier.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-last_activity_at"]
        verbose_name = _("Conversation")
        verbose_name_plural = _("Conversations")

    def __str__(self) -> str:
        return self.title or f"Conversation {self.pk}"

    @property
    def active_run(self):
        return self.runs.filter(status__in=Run.ACTIVE_STATUSES).first()


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", _("User")
        ASSISTANT = "assistant", _("Assistant")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    # Set on user messages: the same key twice means the same send. NULL on
    # assistant messages, so the unique constraint ignores them.
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    # Set on assistant messages: the run that wrote it.
    run = models.OneToOneField("chat.Run", on_delete=models.SET_NULL, null=True, blank=True, related_name="reply")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "idempotency_key"], name="chat_message_idempotency"),
        ]
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")

    def __str__(self) -> str:
        return f"{self.role} message {self.pk}"


class Run(models.Model):
    """One attempt to generate the assistant's reply to a user message."""

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        RUNNING = "running", _("Running")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    ACTIVE_STATUSES = (Status.QUEUED, Status.RUNNING)

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="runs")
    triggering_message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    model_variant = models.ForeignKey(ModelVariant, on_delete=models.SET_NULL, null=True, blank=True)
    prompt = models.ForeignKey(Prompt, on_delete=models.SET_NULL, null=True, blank=True)
    # What was actually used, kept even if the variant or prompt is deleted.
    model_name = models.CharField(max_length=255, blank=True)
    prompt_version = models.CharField(max_length=80, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    error = models.JSONField(default=dict, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = _("Run")
        verbose_name_plural = _("Runs")

    def __str__(self) -> str:
        return f"Run {self.pk} ({self.status})"


class ConversationEvent(models.Model):
    """Audit trail: what happened in a conversation and when. Append-only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="events")
    run = models.ForeignKey(Run, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    type = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = _("Conversation event")
        verbose_name_plural = _("Conversation events")

    def __str__(self) -> str:
        return f"{self.type} ({self.created_at:%Y-%m-%d %H:%M})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            msg = "Conversation events are append-only."
            raise ImmutableRecordError(msg)
        super().save(*args, **kwargs)
