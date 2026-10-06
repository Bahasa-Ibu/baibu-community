from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SubmissionsConfig(AppConfig):
    name = "baibu.submissions"
    verbose_name = _("Submissions")

    def ready(self):
        from . import signals  # noqa: F401
