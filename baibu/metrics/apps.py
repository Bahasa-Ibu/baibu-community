from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MetricsConfig(AppConfig):
    name = "baibu.metrics"
    verbose_name = _("Usage metrics")
