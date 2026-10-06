from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChatConfig(AppConfig):
    name = "baibu.chat"
    verbose_name = _("Chat")

    def ready(self):
        from . import signals  # noqa: F401
