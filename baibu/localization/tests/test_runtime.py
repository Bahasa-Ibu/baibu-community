import shutil
from unittest import mock

import polib
import pytest
from django.core.cache import cache
from django.utils import translation

from baibu.core import storage
from baibu.core.tasks import heartbeat
from baibu.localization import catalogues
from baibu.localization import runtime
from baibu.localization import services
from baibu.localization.models import TranslationCatalogue

from .conftest import TEST_LANGUAGE

pytestmark = pytest.mark.django_db

SIGN_IN = "Sign in"
GOOD_MORNING = "Good morning, example friend"


def _translate(msgid, value):
    po = services.read_draft(TranslationCatalogue.objects.get(language_code=TEST_LANGUAGE))
    entry = po.find(msgid)
    edit = services.Edit(catalogues.entry_key(entry), [value], fuzzy=False, seen=services.fingerprint(entry))
    services.save_entries(TEST_LANGUAGE, [edit], user=None)


def _publish(capture):
    with capture(execute=True):
        return services.publish(TEST_LANGUAGE, user=None)


def _as_a_fresh_process(languages):
    """Forget everything this process loaded, as if it had just started."""
    shutil.rmtree(languages.LOCALIZATION_PUBLISHED_DIR, ignore_errors=True)
    runtime.forget()
    runtime.reset_translation_caches()


def test_published_translations_reach_other_processes(client, source, languages, django_capture_on_commit_callbacks):
    """TC-L10N-05: a process that did not publish loads the new version on its next request."""
    assert client.get(f"/{TEST_LANGUAGE}/").status_code == 404  # no catalogue yet
    _translate(SIGN_IN, "Mlebu")
    _publish(django_capture_on_commit_callbacks)
    _as_a_fresh_process(languages)

    response = client.get(f"/{TEST_LANGUAGE}/")
    assert response.status_code == 200
    assert "Mlebu" in response.content.decode()

    # A later publication elsewhere is announced through the cache.
    _translate(SIGN_IN, "Mlebu maneh")
    with mock.patch.object(services.runtime, "sync"):  # the publishing process is "another" one
        _publish(django_capture_on_commit_callbacks)
    assert "Mlebu maneh" in client.get(f"/{TEST_LANGUAGE}/").content.decode()


def test_checks_are_throttled(client, source, languages, django_capture_on_commit_callbacks):
    languages.LOCALIZATION_SYNC_SECONDS = 60
    runtime.sync_if_due()
    with mock.patch.object(runtime, "materialise") as materialise:
        runtime.sync_if_due()
        materialise.assert_not_called()
        runtime.announce("another-version")
        with mock.patch.object(runtime.time, "monotonic", return_value=runtime.time.monotonic() + 61):
            runtime.sync_if_due()
        materialise.assert_called_once()


def test_sync_can_be_turned_off(source, languages):
    languages.LOCALIZATION_SYNC = False
    with mock.patch.object(runtime, "sync") as sync:
        runtime.sync_if_due()
    sync.assert_not_called()


def test_version_falls_back_to_the_database(source, django_capture_on_commit_callbacks):
    assert runtime.published_version() == runtime.NOTHING_PUBLISHED
    publication = _publish(django_capture_on_commit_callbacks)
    cache.clear()
    assert runtime.published_version() == str(publication.pk)


def test_celery_tasks_load_published_translations(source, languages, django_capture_on_commit_callbacks):
    _translate(GOOD_MORNING, "Sugeng enjing")
    _publish(django_capture_on_commit_callbacks)
    _as_a_fresh_process(languages)
    with translation.override(TEST_LANGUAGE):
        assert translation.gettext(GOOD_MORNING) == GOOD_MORNING
    heartbeat.apply()
    with translation.override(TEST_LANGUAGE):
        assert translation.gettext(GOOD_MORNING) == "Sugeng enjing"


def test_errors_never_reach_the_page(client, source, languages):
    with (
        mock.patch.object(runtime, "materialise", side_effect=RuntimeError("storage down")),
        mock.patch.object(runtime.logger, "exception") as log,
    ):
        assert client.get("/").status_code == 200
    log.assert_called_once()


def test_missing_file_keeps_the_previous_copy_and_retries(source, languages, django_capture_on_commit_callbacks):
    _translate(GOOD_MORNING, "Sugeng enjing")
    publication = _publish(django_capture_on_commit_callbacks)
    target = languages.LOCALIZATION_PUBLISHED_DIR / TEST_LANGUAGE / "LC_MESSAGES" / "django.mo"
    assert target.exists()
    storage.delete(publication.mo_key)
    runtime.forget()
    assert runtime.sync()
    assert target.exists()
    assert runtime._state["loaded"] is None


def test_languages_no_longer_offered_are_removed(source, languages, django_capture_on_commit_callbacks):
    _publish(django_capture_on_commit_callbacks)
    target = languages.LOCALIZATION_PUBLISHED_DIR / TEST_LANGUAGE / "LC_MESSAGES" / "django.mo"
    assert target.exists()
    languages.LANGUAGES = [("en", "English")]
    runtime.sync(force=True)
    assert not target.exists()
    assert not runtime.sync()  # nothing new


def test_published_translations_win_over_deployment_files(source, languages, django_capture_on_commit_callbacks):
    deployment = polib.POFile()
    deployment.metadata = {"Content-Type": "text/plain; charset=UTF-8"}
    deployment.append(polib.POEntry(msgid=GOOD_MORNING, msgstr="From the deployment directory"))
    deployment.append(polib.POEntry(msgid=SIGN_IN, msgstr="Mlebu (file)"))
    target = languages.DEPLOYMENT_DIR / "locale" / TEST_LANGUAGE / "LC_MESSAGES" / "django.mo"
    target.parent.mkdir(parents=True)
    deployment.save_as_mofile(str(target))
    _translate(GOOD_MORNING, "Published")
    _publish(django_capture_on_commit_callbacks)
    with translation.override(TEST_LANGUAGE):
        assert translation.gettext(GOOD_MORNING) == "Published"
        # Messages the published catalogue leaves untranslated still come from the file.
        assert translation.gettext(SIGN_IN) == "Mlebu (file)"


def test_write_failure_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "xx" / "LC_MESSAGES" / "django.mo"
    with (
        mock.patch.object(runtime.Path, "replace", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        runtime._write_atomic(target, b"data")
    assert list(target.parent.iterdir()) == []
