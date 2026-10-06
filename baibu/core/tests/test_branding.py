import pytest

from baibu.core.branding import LanguageConfigError
from baibu.core.branding import build_languages
from baibu.core.branding import parse_extra_languages
from baibu.core.branding import register_extra_languages


def test_parse_extra_languages_reads_names():
    languages = parse_extra_languages("xjv:Javanese:Basa Jawa; xsu:Sundanese")
    assert languages["xjv"]["name"] == "Javanese"
    assert languages["xjv"]["name_local"] == "Basa Jawa"
    # The local name defaults to the English name.
    assert languages["xsu"]["name_local"] == "Sundanese"


def test_parse_extra_languages_ignores_blank_entries():
    assert parse_extra_languages(" ; ;") == {}
    assert parse_extra_languages("") == {}


@pytest.mark.parametrize("spec", ["xx", "xx:", ":Name"])
def test_parse_extra_languages_rejects_incomplete_entries(spec):
    with pytest.raises(LanguageConfigError):
        parse_extra_languages(spec)


def test_build_languages_uses_local_names_and_drops_duplicates():
    assert build_languages(["en", "fr", "en", " "], default="en") == [("en", "English"), ("fr", "français")]


def test_build_languages_accepts_registered_extra_language():
    register_extra_languages("xqa:Test language:Basa Tes")
    assert build_languages(["en", "xqa"], default="xqa") == [("en", "English"), ("xqa", "Basa Tes")]


def test_build_languages_rejects_unknown_code():
    with pytest.raises(LanguageConfigError, match="Unknown language code"):
        build_languages(["en", "zz-unknown"], default="en")


def test_build_languages_requires_default_in_list():
    with pytest.raises(LanguageConfigError, match="must be listed"):
        build_languages(["en"], default="fr")
