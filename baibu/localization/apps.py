from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class LocalizationConfig(AppConfig):
    name = "baibu.localization"
    verbose_name = _("Translations")

    def ready(self) -> None:
        # Nothing here touches the database or file storage: published
        # translations load on a process's first request or task.
        from celery.signals import task_prerun

        from . import runtime
        from .permissions import ensure_translators_group

        post_migrate.connect(ensure_translators_group, sender=self, dispatch_uid="localization.translators_group")
        task_prerun.connect(runtime.sync_before_task, weak=False, dispatch_uid="localization.sync_before_task")
