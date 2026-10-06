from unittest import mock

import polib
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from baibu.localization import catalogues
from baibu.localization import services
from baibu.localization.extraction import ExtractionError
from baibu.localization.models import TranslationCatalogue
from baibu.localization.models import TranslationPublication
from baibu.localization.models import TranslationSource
from baibu.users.tests.factories import UserFactory

from .conftest import TEST_LANGUAGE

pytestmark = pytest.mark.django_db

INDEX_URL = reverse("localization:index")
CATALOGUE_URL = reverse("localization:catalogue", args=[TEST_LANGUAGE])
GOOD_MORNING = "Good morning, example friend"
GREETING = "Welcome to the example market, %(name)s."
BASKET = "%(count)s example basket"


def _draft():
    return services.read_draft(TranslationCatalogue.objects.get(language_code=TEST_LANGUAGE))


def _form_data(*changes):
    """POST data for the editor: (msgid, [values], fuzzy) per entry."""
    draft = _draft()
    data = {"key": []}
    for msgid, values, fuzzy in changes:
        entry = draft.find(msgid)
        key = catalogues.entry_key(entry)
        data["key"].append(key)
        data[f"seen-{key}"] = services.fingerprint(entry)
        for index, value in enumerate(values):
            data[f"msgstr-{key}-{index}"] = value
        if fuzzy:
            data[f"fuzzy-{key}"] = "on"
    return data


def test_pages_need_the_permission(client, source, user):
    """TC-L10N-03: only translators reach the pages."""
    urls = [
        INDEX_URL,
        CATALOGUE_URL,
        reverse("localization:history", args=[TEST_LANGUAGE]),
        reverse("localization:download", args=[TEST_LANGUAGE]),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("account_login") in response.url
    client.force_login(user)
    for url in urls:
        assert client.get(url).status_code == 403
    assert client.post(reverse("localization:publish", args=[TEST_LANGUAGE])).status_code == 403
    assert not TranslationPublication.objects.exists()


def test_superusers_and_permission_holders_may_translate(client, source):
    admin = UserFactory(email="admin@example.org", is_superuser=True)
    client.force_login(admin)
    assert client.get(INDEX_URL).status_code == 200


def test_nav_links_translators_to_the_pages(translator_client, languages):
    assert 'href="/translations/"' in translator_client.get("/").content.decode()


def test_index_before_and_after_extracting(translator_client, languages):
    content = translator_client.get(INDEX_URL).content.decode()
    assert "have not been extracted" in content
    assert "Exampleish" in content
    assert "Not started." in content
    with mock.patch("baibu.localization.views.services.update_sources", side_effect=ExtractionError("boom")):
        response = translator_client.post(reverse("localization:update_sources"), follow=True)
    assert "could not be extracted" in response.content.decode()

    response = translator_client.post(reverse("localization:update_sources"), follow=True)
    assert "Source strings updated" in response.content.decode()
    source = TranslationSource.objects.get()
    assert source.created_by.email == "translator@example.org"
    assert source.entry_count > 100  # the real code
    response = translator_client.post(reverse("localization:update_sources"), follow=True)
    content = response.content.decode()
    assert "have not changed" in content
    assert "0 of" in content
    assert "Nothing published yet." in content


def test_index_survives_a_missing_draft(translator_client, source):
    catalogue = TranslationCatalogue.objects.get()
    catalogue.draft_key = "translations/missing.po"
    catalogue.save()
    assert translator_client.get(INDEX_URL).status_code == 200


def test_only_english_means_nothing_to_translate(translator_client, settings):
    settings.LANGUAGES = [("en", "English")]
    assert "only in English" in translator_client.get(INDEX_URL).content.decode()


def test_unknown_language_is_not_found(translator_client, source):
    for code in ("en", "zz"):
        assert translator_client.get(reverse("localization:catalogue", args=[code])).status_code == 404


def test_catalogue_needs_sources(translator_client, languages):
    response = translator_client.get(CATALOGUE_URL)
    assert response.status_code == 302
    assert response.url == INDEX_URL


def test_filters_and_search(translator_client, source):
    services.save_entries(
        TEST_LANGUAGE,
        [services.Edit(**{**_edit_args(GOOD_MORNING), "values": ["Sugeng enjing"]})],
        user=None,
    )
    content = translator_client.get(CATALOGUE_URL).content.decode()
    assert "Untranslated (4)" in content
    assert GOOD_MORNING not in content
    content = translator_client.get(CATALOGUE_URL, {"state": "translated"}).content.decode()
    assert GOOD_MORNING in content
    assert "Sign in" not in content
    content = translator_client.get(CATALOGUE_URL, {"state": "all", "q": "ENJING"}).content.decode()
    assert GOOD_MORNING in content
    assert "Sign in" not in content
    content = translator_client.get(CATALOGUE_URL, {"state": "bogus", "q": "nothing like this"}).content.decode()
    assert "No messages match." in content
    content = translator_client.get(CATALOGUE_URL, {"state": "all"}).content.decode()
    assert "Form 1 (n = 1…)" in content
    assert "Context: month name" in content
    assert "example/templates/page.html:3" in content


def _edit_args(msgid):
    entry = _draft().find(msgid)
    return {"key": catalogues.entry_key(entry), "values": [], "fuzzy": False, "seen": services.fingerprint(entry)}


def test_pagination(translator_client, source, monkeypatch):
    monkeypatch.setattr("baibu.localization.views.PAGE_SIZE", 2)
    content = translator_client.get(CATALOGUE_URL, {"state": "all", "page": 2}).content.decode()
    assert "Page 2 of 3" in content
    assert "Previous" in content
    assert "Next" in content


def test_save_draft(translator_client, source):
    """TC-L10N-03: translators edit entries, including plural forms, and save a draft."""
    data = _form_data(
        (GOOD_MORNING, ["Sugeng enjing"], False),
        (BASKET, ["%(count)s kranjang", "%(count)s kranjang-kranjang"], True),
    )
    response = translator_client.post(f"{CATALOGUE_URL}?state=all", data)
    assert response.status_code == 302
    assert response.url == f"{CATALOGUE_URL}?state=all"
    draft = _draft()
    assert draft.find(GOOD_MORNING).msgstr == "Sugeng enjing"
    assert draft.find(BASKET).msgstr_plural == {0: "%(count)s kranjang", 1: "%(count)s kranjang-kranjang"}
    assert draft.find(BASKET).fuzzy
    content = translator_client.get(response.url).content.decode()
    assert "2 translations saved." in content
    assert "Unpublished changes" in content


def test_invalid_translation_is_shown_again(translator_client, source):
    """TC-L10N-07: the page keeps what the translator typed and explains the problem."""
    data = _form_data((GREETING, ["Sugeng rawuh, %(jeneng)s."], False), (GOOD_MORNING, ["Esuk"], False))
    response = translator_client.post(CATALOGUE_URL, data)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Some translations were not saved" in content
    assert "Unknown placeholder" in content
    assert "Sugeng rawuh, %(jeneng)s." in content
    assert "1 translation saved." in content
    assert _draft().find(GREETING).msgstr == ""


def test_conflicting_edit_is_reported(translator_client, source):
    """TC-L10N-08."""
    data = _form_data((GOOD_MORNING, ["Mine"], False))
    services.save_entries(
        TEST_LANGUAGE, [services.Edit(**{**_edit_args(GOOD_MORNING), "values": ["Theirs"]})], user=None
    )
    response = translator_client.post(CATALOGUE_URL, data, follow=True)
    assert "changed by someone else" in response.content.decode()
    assert _draft().find(GOOD_MORNING).msgstr == "Theirs"


def test_plural_forms(translator_client, source):
    url = reverse("localization:plural_forms", args=[TEST_LANGUAGE])
    response = translator_client.post(url, {"plural_forms": "nplurals=1; plural=0;"}, follow=True)
    assert "Plural forms saved." in response.content.decode()
    assert catalogues.plural_forms(_draft()) == "nplurals=1; plural=0;"
    response = translator_client.post(url, {"plural_forms": "nplurals=two"}, follow=True)
    assert "Plural forms must look like" in response.content.decode()


def test_download_and_upload(translator_client, source):
    response = translator_client.get(reverse("localization:download", args=[TEST_LANGUAGE]))
    assert response["Content-Disposition"] == 'attachment; filename="xx.po"'
    po = catalogues.parse(response.content)
    po.find(GOOD_MORNING).msgstr = "Saka berkas"
    po.find(GREETING).msgstr = "Rawuh %(liyane)s"
    url = reverse("localization:upload", args=[TEST_LANGUAGE])
    upload = SimpleUploadedFile("xx.po", str(po).encode())
    content = translator_client.post(url, {"file": upload}, follow=True).content.decode()
    assert "1 translation taken from the file." in content
    assert "1 translation was skipped" in content
    assert _draft().find(GOOD_MORNING).msgstr == "Saka berkas"

    garbage = SimpleUploadedFile("xx.po", b"garbage\n")
    content = translator_client.post(url, {"file": garbage}, follow=True).content.decode()
    assert "not a valid PO file" in content
    with mock.patch("baibu.localization.forms.MAX_UPLOAD_BYTES", 3):
        content = translator_client.post(url, {"file": SimpleUploadedFile("xx.po", b"long")}, follow=True)
    assert "too large" in content.content.decode()


def test_publish_and_see_the_page_in_the_new_language(
    translator_client, source, translator, django_capture_on_commit_callbacks
):
    """TC-L10N-04: publishing makes a rendered page use the translation, with an audit row."""
    translator_client.post(CATALOGUE_URL, _form_data(("Sign in", ["Mlebu"], False)))
    with django_capture_on_commit_callbacks(execute=True):
        response = translator_client.post(reverse("localization:publish", args=[TEST_LANGUAGE]), follow=True)
    assert "Published version 1." in response.content.decode()
    publication = TranslationPublication.objects.get()
    assert publication.published_by == translator
    assert publication.translated_count == 1
    translator_client.logout()
    assert "Mlebu" in translator_client.get(f"/{TEST_LANGUAGE}/").content.decode()


def test_history_and_restore(translator_client, source, translator):
    """TC-L10N-06."""
    history_url = reverse("localization:history", args=[TEST_LANGUAGE])
    assert "Nothing has been published" in translator_client.get(history_url).content.decode()
    first = services.publish(TEST_LANGUAGE, user=translator)
    services.publish(TEST_LANGUAGE, user=None)
    content = translator_client.get(history_url).content.decode()
    assert "Version 2" in content
    assert "Restore" in content
    assert translator.name in content
    response = translator_client.post(reverse("localization:restore", args=[TEST_LANGUAGE, first.pk]), follow=True)
    content = response.content.decode()
    assert "Version 1 is live again, as version 3." in content
    assert "A restore of version 1." in content
    other = TranslationPublication.objects.create(language_code="fr", version=1, po_key="a", mo_key="b")
    assert translator_client.post(reverse("localization:restore", args=[TEST_LANGUAGE, other.pk])).status_code == 404


def test_editor_shows_live_version(translator_client, source):
    services.publish(TEST_LANGUAGE, user=None)
    content = translator_client.get(CATALOGUE_URL).content.decode()
    assert "Live: version 1" in content
    assert "Unpublished changes" not in content


def test_upload_reaches_only_messages_in_the_draft(translator_client, source):
    po = polib.POFile()
    po.append(polib.POEntry(msgid="Unrelated example", msgstr="Liyane"))
    url = reverse("localization:upload", args=[TEST_LANGUAGE])
    content = translator_client.post(url, {"file": SimpleUploadedFile("x.po", str(po).encode())}, follow=True)
    assert "0 translations taken from the file." in content.content.decode()


def test_plural_labels():
    from baibu.localization.views import _plural_labels

    po = polib.POFile()
    po.metadata["Plural-Forms"] = "nonsense"
    assert _plural_labels(po) == ["Form 1 (n = 1…)", "Form 2 (n = 2…)"]
    po.metadata["Plural-Forms"] = "nplurals=3; plural=(n==1 ? 0 : 1);"
    assert _plural_labels(po)[2] == "Form 3"
