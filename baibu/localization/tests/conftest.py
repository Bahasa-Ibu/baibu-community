"""Fixtures for the translation workflow. All strings are invented for the tests.

``xx`` ("Exampleish") is a made-up language that Django does not ship, so any
translation the tests see comes from the workflow under test.
"""

from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django.utils import translation

from baibu.core.branding import register_extra_languages
from baibu.localization import runtime
from baibu.localization import services
from baibu.localization.extraction import SourceRoot
from baibu.localization.permissions import TRANSLATORS_GROUP
from baibu.users.tests.factories import UserFactory

TEST_LANGUAGE = "xx"

TEMPLATE = (
    "{% load i18n %}\n"
    '{% translate "Sign in" %}\n'
    '{% translate "Good morning, example friend" %}\n'
    "{% blocktranslate count count=n %}{{ count }} example basket{% plural %}"
    "{{ count }} example baskets{% endblocktranslate %}\n"
)
PYTHON = """from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

GREETING = _("Welcome to the example market, %(name)s.")
MONTH = pgettext_lazy("month name", "May")
"""


@pytest.fixture(autouse=True)
def _translation_state():
    runtime.forget()
    yield
    runtime.forget()
    translation.deactivate()


@pytest.fixture
def code_dir(tmp_path) -> Path:
    """A tiny code tree to extract strings from."""
    root = tmp_path / "code"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "page.html").write_text(TEMPLATE, encoding="utf-8")
    (root / "strings.py").write_text(PYTHON, encoding="utf-8")
    return root


@pytest.fixture
def roots(code_dir) -> list[SourceRoot]:
    return [SourceRoot(code_dir, "example")]


@pytest.fixture
def languages(settings, tmp_path):
    """Enable English and the test language, with published and deployment catalogues in tmp_path."""
    register_extra_languages(f"{TEST_LANGUAGE}:Exampleish:Exampleish")
    published = tmp_path / "published"
    deployment = tmp_path / "deployment"
    (deployment / "locale").mkdir(parents=True)
    settings.LANGUAGES = [("en", "English"), (TEST_LANGUAGE, "Exampleish")]
    settings.LOCALIZATION_PUBLISHED_DIR = published
    settings.DEPLOYMENT_DIR = deployment
    settings.LOCALE_PATHS = [str(published), str(deployment / "locale")]
    settings.LOCALIZATION_SYNC = True
    settings.LOCALIZATION_SYNC_SECONDS = 0
    return settings


@pytest.fixture
def source(db, languages, roots):
    return services.update_sources(roots=roots).source


@pytest.fixture
def translator(db):
    person = UserFactory(email="translator@example.org")
    person.groups.add(Group.objects.get(name=TRANSLATORS_GROUP))
    return person


@pytest.fixture
def translator_client(client, translator):
    client.force_login(translator)
    return client
