from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "baibu.core"
    verbose_name = "Core"

    def ready(self) -> None:
        from django.apps import apps

        from .sites import sync_site_from_settings

        # This app has no models, so it never receives post_migrate itself.
        post_migrate.connect(
            sync_site_from_settings,
            sender=apps.get_app_config("sites"),
            dispatch_uid="core.sync_site_from_settings",
        )
