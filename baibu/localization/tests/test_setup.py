"""The management command, the translators group and the admin."""

from io import StringIO
from unittest import mock

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import CommandError
from django.core.management import call_command
from django.urls import reverse

from baibu.localization import services
from baibu.localization.extraction import ExtractionError
from baibu.localization.models import TranslationPublication
from baibu.localization.permissions import PERMISSION
from baibu.localization.permissions import TRANSLATORS_GROUP
from baibu.localization.permissions import ensure_translators_group
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _run(*args) -> str:
    out = StringIO()
    call_command("update_translation_sources", *args, stdout=out)
    return out.getvalue()


def test_command_with_only_english(settings):
    settings.LANGUAGES = [("en", "English")]
    assert "nothing to translate" in _run()


def test_command_extracts_and_merges(languages, roots):
    real = services.update_sources

    with mock.patch.object(services, "update_sources", lambda **kw: real(roots=roots, **kw)):
        assert _run() == "Source strings updated (5 messages). Drafts updated: xx.\n"
        assert _run() == "Source strings unchanged (5 messages). Drafts updated: none.\n"
        assert _run("--force").startswith("Source strings updated")


def test_command_reports_extraction_errors(languages):
    with (
        mock.patch.object(services, "update_sources", side_effect=ExtractionError("no xgettext")),
        pytest.raises(CommandError, match="no xgettext"),
    ):
        _run()


def test_translators_group_has_the_permission():
    Group.objects.filter(name=TRANSLATORS_GROUP).delete()
    ensure_translators_group()
    ensure_translators_group()
    member = UserFactory()
    member.groups.add(Group.objects.get(name=TRANSLATORS_GROUP))
    assert member.has_perm(PERMISSION)


def test_sync_middleware_runs_before_the_language_is_chosen():
    middleware = settings.MIDDLEWARE
    assert middleware.index("baibu.localization.middleware.TranslationSyncMiddleware") < middleware.index(
        "django.middleware.locale.LocaleMiddleware"
    )
    assert settings.LOCALE_PATHS[0] == str(settings.LOCALIZATION_PUBLISHED_DIR)


def test_admin_is_read_only(client, source):
    services.publish("xx", user=None)
    admin = UserFactory(email="admin@example.org", is_staff=True, is_superuser=True)
    client.force_login(admin)
    for name in ("translationpublication", "translationcatalogue", "translationsource"):
        assert client.get(reverse(f"admin:localization_{name}_changelist")).status_code == 200
        assert client.get(reverse(f"admin:localization_{name}_add")).status_code == 403
    publication = TranslationPublication.objects.get()
    assert (
        client.get(reverse("admin:localization_translationpublication_change", args=[publication.pk])).status_code
        == 200
    )
    assert str(publication) == "xx v1"
    assert str(source).startswith("Source strings of ")
    assert str(services.get_catalogue("xx")) == "xx"
