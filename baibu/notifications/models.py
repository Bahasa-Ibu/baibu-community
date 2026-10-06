import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """A message for one user, shown in their in-app inbox."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    # What it is about, e.g. "submission_accepted". Registered kinds (see
    # kinds.py) are translated when shown, using ``params``; other kinds show
    # the stored title and body.
    kind = models.CharField(max_length=64)
    params = models.JSONField(default=dict, blank=True)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    # A path inside the platform to open, e.g. /contribute/.
    link = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"], name="notification_user_unread")]
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")

    def __str__(self) -> str:
        return str(self.display_title)

    def _render(self, text) -> str:
        try:
            return str(text) % self.params if self.params else str(text)
        except (KeyError, TypeError, ValueError):
            return str(text)

    @property
    def display_title(self) -> str:
        from .kinds import KINDS

        kind = KINDS.get(self.kind)
        return self._render(kind.title) if kind else self.title

    @property
    def display_body(self) -> str:
        from .kinds import KINDS

        kind = KINDS.get(self.kind)
        return self._render(kind.body) if kind else self.body

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
