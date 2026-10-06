"""Who may translate.

Anyone with the ``localization.edit_translations`` permission may edit and
publish translations. A ``translators`` group with that permission is created
on ``migrate``; add people to it in the admin.
"""

PERMISSION = "localization.edit_translations"
TRANSLATORS_GROUP = "translators"


def ensure_translators_group(**kwargs) -> None:
    from django.contrib.auth.models import Group
    from django.contrib.auth.models import Permission

    permission = Permission.objects.filter(
        content_type__app_label="localization", codename="edit_translations"
    ).first()
    if permission is None:  # pragma: no cover - created by the same migrate run
        return
    group, _created = Group.objects.get_or_create(name=TRANSLATORS_GROUP)
    group.permissions.add(permission)
