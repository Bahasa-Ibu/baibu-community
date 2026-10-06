import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class DailyMetric(models.Model):
    """One aggregate count for one day: never text, names or per-user rows.

    ``name`` is a metric from ``baibu.metrics.definitions.METRICS``.
    ``dimension`` is empty for a plain total, or the value a breakdown is
    split by (a language code, a status, ``scope:tier``, a week number).
    Retention rows are dated by the first day of the cohort week.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    date = models.DateField(db_index=True)
    name = models.CharField(max_length=64)
    dimension = models.CharField(max_length=128, blank=True, default="")
    value = models.BigIntegerField()
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "name", "dimension"]
        constraints = [
            models.UniqueConstraint(fields=["date", "name", "dimension"], name="metrics_one_value_per_day"),
        ]
        indexes = [models.Index(fields=["name", "date"])]
        verbose_name = _("Daily metric")
        verbose_name_plural = _("Daily metrics")

    def __str__(self) -> str:
        suffix = f" [{self.dimension}]" if self.dimension else ""
        return f"{self.date} {self.name}{suffix}: {self.value}"
