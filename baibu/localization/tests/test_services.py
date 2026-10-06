import polib
import pytest
from django.utils import translation

from baibu.core import storage
from baibu.localization import catalogues
from baibu.localization import services
from baibu.localization.extraction import SourceRoot
from baibu.localization.models import TranslationCatalogue
from baibu.localization.models import TranslationPublication
from baibu.localization.models import TranslationSource

from .conftest import TEST_LANGUAGE

pytestmark = pytest.mark.django_db

GOOD_MORNING = "Good morning, example friend"
GREETING = "Welcome to the example market, %(name)s."
BASKET = "%(count)s example basket"


def _draft(language_code=TEST_LANGUAGE) -> polib.POFile:
    return services.read_draft(TranslationCatalogue.objects.get(language_code=language_code))


def _find(po, msgid, msgctxt=None):
    return po.find(msgid, msgctxt=msgctxt) if msgctxt else po.find(msgid)


def _edit(msgid, *values, fuzzy=False, msgctxt=None, user=None):
    entry = _find(_draft(), msgid, msgctxt)
    edit = services.Edit(catalogues.entry_key(entry), list(values), fuzzy, services.fingerprint(entry))
    return services.save_entries(TEST_LANGUAGE, [edit], user=user)


def test_update_sources_creates_a_draft_per_language(source, settings):
    """TC-L10N-01."""
    assert source.entry_count == 5
    assert storage.exists(source.pot_key)
    catalogue = TranslationCatalogue.objects.get()
    assert catalogue.language_code == TEST_LANGUAGE
    assert catalogue.source == source
    draft = _draft()
    assert draft.metadata["Language"] == TEST_LANGUAGE
    assert catalogues.stats(draft).total == 5
    # English is the source language: nothing to translate.
    assert services.translatable_languages() == [(TEST_LANGUAGE, "Exampleish")]


def test_unchanged_sources_are_not_stored_again(source, roots):
    result = services.update_sources(roots=roots)
    assert not result.created
    assert result.merged == []
    assert TranslationSource.objects.count() == 1
    assert services.update_sources(roots=roots, force=True).created


def test_new_sources_merge_into_drafts_keeping_translations(
    source, code_dir, roots, django_capture_on_commit_callbacks
):
    """TC-L10N-02."""
    _edit(GOOD_MORNING, "Selamat pagi, kanca conto")
    old_key = TranslationCatalogue.objects.get().draft_key
    (code_dir / "strings.py").write_text(
        'from django.utils.translation import gettext_lazy as _\nNEW = _("A brand new example message")\n'
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = services.update_sources(roots=roots)
    assert result.created
    assert result.merged == [TEST_LANGUAGE]
    draft = _draft()
    assert draft.find(GOOD_MORNING).msgstr == "Selamat pagi, kanca conto"
    assert draft.find("A brand new example message").msgstr == ""
    removed = draft.find(GREETING, include_obsolete_entries=True)
    assert removed.obsolete
    assert not storage.exists(old_key)


def test_new_language_starts_from_the_deployment_catalogue(languages, roots, tmp_path):
    seed = polib.POFile()
    seed.metadata = {"Content-Type": "text/plain; charset=UTF-8", "Plural-Forms": "nplurals=1; plural=0;"}
    seed.append(polib.POEntry(msgid=GOOD_MORNING, msgstr="Esuk, kanca"))
    seed.append(polib.POEntry(msgid="A message no longer in the code", msgstr="Lawas"))
    target = tmp_path / "deployment" / "locale" / TEST_LANGUAGE / "LC_MESSAGES" / "django.po"
    target.parent.mkdir(parents=True)
    seed.save(str(target))
    services.update_sources(roots=roots)
    draft = _draft()
    assert draft.find(GOOD_MORNING).msgstr == "Esuk, kanca"
    assert catalogues.plural_forms(draft) == "nplurals=1; plural=0;"
    assert draft.find(BASKET).msgstr_plural == {0: ""}


def test_invalid_deployment_catalogue_is_ignored(languages, roots, tmp_path):
    target = tmp_path / "deployment" / "locale" / TEST_LANGUAGE / "LC_MESSAGES" / "django.po"
    target.parent.mkdir(parents=True)
    target.write_text("garbage\n")
    services.update_sources(roots=roots)
    assert catalogues.stats(_draft()).translated == 0


def test_get_catalogue(languages, roots):
    with pytest.raises(services.UnknownLanguageError):
        services.get_catalogue("en")
    with pytest.raises(services.NoSourceError):
        services.get_catalogue(TEST_LANGUAGE)
    # A language added after the sources were extracted gets its draft on first use.
    TranslationSource.objects.create(pot_key=storage.save_bytes("t/x.pot", b""), content_hash="x")
    catalogue = services.get_catalogue(TEST_LANGUAGE)
    assert catalogue.language_code == TEST_LANGUAGE


def test_save_entries_including_plurals(source, translator):
    """TC-L10N-03 (service level)."""
    result = _edit(GOOD_MORNING, "Sugeng enjing", user=translator)
    assert result.changed == 1
    result = _edit(BASKET, "%(count)s kranjang siji", "%(count)s kranjang akeh")
    assert result.changed == 1
    result = _edit("May", "Mei", msgctxt="month name")
    draft = _draft()
    assert draft.find(GOOD_MORNING).msgstr == "Sugeng enjing"
    assert draft.find(BASKET).msgstr_plural == {0: "%(count)s kranjang siji", 1: "%(count)s kranjang akeh"}
    assert TranslationCatalogue.objects.get().updated_by is None
    # Saving the same values again changes nothing.
    assert _edit(GOOD_MORNING, "Sugeng enjing").changed == 0


def test_fuzzy_flag_and_clearing_it(source):
    _edit(GOOD_MORNING, "Sugeng enjing", fuzzy=True)
    entry = _draft().find(GOOD_MORNING)
    assert entry.fuzzy
    assert catalogues.entry_state(entry) == "fuzzy"
    _edit(GOOD_MORNING, "Sugeng enjing", fuzzy=False)
    assert catalogues.entry_state(_draft().find(GOOD_MORNING)) == "translated"
    # An empty translation cannot be marked for review.
    _edit(GOOD_MORNING, "", fuzzy=True)
    assert catalogues.entry_state(_draft().find(GOOD_MORNING)) == "untranslated"


def test_broken_placeholders_are_refused(source):
    """TC-L10N-07."""
    result = _edit(GREETING, "Sugeng rawuh, %(jeneng)s.")
    assert result.changed == 0
    assert "%(jeneng)s" in next(iter(result.errors.values()))
    assert _draft().find(GREETING).msgstr == ""


def test_someone_elses_change_is_not_overwritten(source):
    """TC-L10N-08."""
    entry = _draft().find(GOOD_MORNING)
    stale = services.Edit(catalogues.entry_key(entry), ["Mine"], fuzzy=False, seen=services.fingerprint(entry))
    _edit(GOOD_MORNING, "Theirs")
    result = services.save_entries(TEST_LANGUAGE, [stale], user=None)
    assert result.conflicts == [stale.key]
    assert _draft().find(GOOD_MORNING).msgstr == "Theirs"
    missing = services.Edit("0" * 16, ["x"], fuzzy=False, seen="")
    assert services.save_entries(TEST_LANGUAGE, [missing], user=None).conflicts == ["0" * 16]


def test_set_plural_forms_resizes_plural_entries(source):
    services.set_plural_forms(TEST_LANGUAGE, "nplurals=3; plural=(n==1 ? 0 : n==2 ? 1 : 2);", user=None)
    assert _draft().find(BASKET).msgstr_plural == {0: "", 1: "", 2: ""}
    with pytest.raises(catalogues.CatalogueError):
        services.set_plural_forms(TEST_LANGUAGE, "nonsense", user=None)


def test_import_catalogue(source):
    upload = polib.POFile()
    upload.append(polib.POEntry(msgid=GOOD_MORNING, msgstr="Enjing"))
    upload.append(polib.POEntry(msgid=GREETING, msgstr="Rawuh %(liyane)s", flags=["python-format"]))
    upload.append(
        polib.POEntry(msgid=BASKET, msgid_plural="%(count)s example baskets", msgstr_plural={0: "a", 1: "b"})
    )
    upload.append(polib.POEntry(msgid="Not in the draft", msgstr="Ora"))
    upload.append(polib.POEntry(msgid="May", msgctxt="month name"))
    result = services.import_catalogue(TEST_LANGUAGE, str(upload).encode(), user=None)
    assert result.changed == 2
    assert len(result.errors) == 1
    draft = _draft()
    assert draft.find(GOOD_MORNING).msgstr == "Enjing"
    assert draft.find(BASKET).msgstr_plural == {0: "a", 1: "b"}
    assert draft.find("Not in the draft") is None


def test_publish_makes_translations_live(source, translator, django_capture_on_commit_callbacks):
    """TC-L10N-04 (service level): gettext returns the published translation."""
    _edit(GOOD_MORNING, "Sugeng enjing, kanca conto")
    _edit(BASKET, "%(count)s kranjang", "%(count)s kranjang-kranjang")
    _edit(GREETING, "Sugeng rawuh, %(name)s.", fuzzy=True)
    with django_capture_on_commit_callbacks(execute=True):
        publication = services.publish(TEST_LANGUAGE, user=translator)
    assert publication.version == 1
    assert (publication.translated_count, publication.fuzzy_count, publication.total_count) == (2, 1, 5)
    assert publication.published_by == translator
    with translation.override(TEST_LANGUAGE):
        assert translation.gettext(GOOD_MORNING) == "Sugeng enjing, kanca conto"
        assert translation.ngettext(BASKET, "%(count)s example baskets", 3) == "%(count)s kranjang-kranjang"
        # Entries marked for review are not published.
        assert translation.gettext(GREETING) == GREETING


def test_publish_is_versioned_and_restorable(source, translator, django_capture_on_commit_callbacks):
    """TC-L10N-06."""
    _edit(GOOD_MORNING, "First")
    with django_capture_on_commit_callbacks(execute=True):
        first = services.publish(TEST_LANGUAGE, user=translator)
    _edit(GOOD_MORNING, "Second")
    with django_capture_on_commit_callbacks(execute=True):
        second = services.publish(TEST_LANGUAGE, user=translator)
    assert second.version == 2
    with translation.override(TEST_LANGUAGE):
        assert translation.gettext(GOOD_MORNING) == "Second"
    with django_capture_on_commit_callbacks(execute=True):
        restored = services.restore(first, user=translator)
    assert restored.version == 3
    assert restored.restored_from == first
    assert restored.mo_key == first.mo_key
    with translation.override(TEST_LANGUAGE):
        assert translation.gettext(GOOD_MORNING) == "First"
    # The draft keeps the newer work.
    assert _draft().find(GOOD_MORNING).msgstr == "Second"
    assert services.has_unpublished_changes(_draft(), restored)
    assert services.latest_publication(TEST_LANGUAGE) == restored
    assert TranslationPublication.objects.count() == 3


def test_has_unpublished_changes(source):
    assert services.has_unpublished_changes(_draft(), None)
    publication = services.publish(TEST_LANGUAGE, user=None)
    assert not services.has_unpublished_changes(_draft(), publication)
    _edit(GOOD_MORNING, "Changed")
    assert services.has_unpublished_changes(_draft(), publication)


def test_failed_publication_record_removes_its_files(source, monkeypatch):
    saved = []
    original = storage.save_bytes

    def tracking_save(key, data):
        saved.append(original(key, data))
        return saved[-1]

    def fail(**kwargs):
        raise RuntimeError

    monkeypatch.setattr("baibu.localization.services.storage.save_bytes", tracking_save)
    monkeypatch.setattr(TranslationPublication.objects, "create", fail)
    with pytest.raises(RuntimeError):
        services.publish(TEST_LANGUAGE, user=None)
    assert len(saved) == 2
    assert not any(storage.exists(key) for key in saved)


def test_missing_draft_file_is_an_error(source):
    catalogue = TranslationCatalogue.objects.get()
    storage.delete(catalogue.draft_key)
    with pytest.raises(FileNotFoundError):
        services.read_draft(catalogue)


def test_failed_source_record_removes_the_template(languages, roots, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError

    monkeypatch.setattr(TranslationSource.objects, "create", fail)
    with pytest.raises(RuntimeError):
        services.update_sources(roots=roots)
    assert TranslationSource.objects.count() == 0


def test_failed_draft_save_removes_the_new_file(source, monkeypatch):
    saved = []
    original = storage.save_bytes

    def tracking_save(key, data):
        saved.append(original(key, data))
        return saved[-1]

    def fail(self, *args, **kwargs):
        raise RuntimeError

    monkeypatch.setattr("baibu.localization.services.storage.save_bytes", tracking_save)
    monkeypatch.setattr(TranslationCatalogue, "save", fail)
    with pytest.raises(RuntimeError):
        _edit(GOOD_MORNING, "Lost")
    assert saved
    assert not storage.exists(saved[-1])


def test_other_roots_are_isolated(languages, tmp_path):
    (tmp_path / "solo.py").write_text('from django.utils.translation import gettext as _\n_("Solo example")\n')
    source = services.update_sources(roots=[SourceRoot(tmp_path, "solo")]).source
    assert source.entry_count == 1
