from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StaffConfig(AppConfig):
    name = "baibu.staff"
    verbose_name = _("Staff")
