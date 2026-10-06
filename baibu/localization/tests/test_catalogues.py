import polib
import pytest

from baibu.localization import catalogues


def _entry(msgid, msgid_plural="", flags=("python-format",)):
    return polib.POEntry(msgid=msgid, msgid_plural=msgid_plural, flags=list(flags))


@pytest.mark.parametrize(
    ("msgid", "translation", "problem"),
    [
        ("Hello %(name)s.", "Halo %(name)s.", None),
        ("Hello %(name)s.", "Halo.", None),
        ("Hello %(name)s.", "Halo %(nama)s.", "Unknown placeholder: %(nama)s"),
        ("Hello %(name)s.", "Halo 100% %(name)s.", "percent sign"),
        ("Hello %(name)s.", "Halo %(name)s 100%", "percent sign"),
        ("Hello %(name)s.", "Halo %(name)s 100%!", "percent sign"),
        ("Hello %(name)s, 100%%.", "Halo %(name)s, 100%%.", None),
        ("%s of %s", "%s dari %s", None),
        ("%s of %s", "%s", "same number"),
    ],
)
def test_placeholder_problem(msgid, translation, problem):
    result = catalogues.placeholder_problem(_entry(msgid), translation)
    if problem is None:
        assert result is None
    else:
        assert problem in result


def test_placeholders_only_checked_for_python_format():
    assert catalogues.placeholder_problem(_entry("50% off", flags=()), "50% off") is None


def test_plural_placeholders_may_come_from_either_form():
    entry = _entry("one basket", "%(count)d baskets")
    assert catalogues.placeholder_problem(entry, "satu keranjang", "%(count)d keranjang") is None
    assert catalogues.placeholder_problem(entry, "", "%(jumlah)d keranjang")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("plural=0;", "must look like"),
        ("nplurals=0; plural=0;", "between 1 and"),
        ("nplurals=9; plural=0;", "between 1 and"),
        ("nplurals=2; plural=(n => 1);", "not valid"),
    ],
)
def test_invalid_plural_forms(value, message):
    with pytest.raises(catalogues.CatalogueError, match=message):
        catalogues.parse_plural_forms(value)


def test_plural_examples_label_each_form():
    assert catalogues.plural_examples("nplurals=2; plural=(n != 1);") == [[1], [0, 2, 3]]
    assert catalogues.plural_examples("nplurals=1; plural=0;") == [[0, 1, 2]]


def test_known_plural_forms(monkeypatch):
    assert catalogues.known_plural_forms("fr").startswith("nplurals=")
    assert catalogues.known_plural_forms("xx") is None
    monkeypatch.setattr(catalogues.polib, "pofile", lambda path: polib.POFile())
    assert catalogues.known_plural_forms("fr") is None


def test_plural_count_falls_back_on_a_broken_header():
    po = polib.POFile()
    po.metadata["Plural-Forms"] = "nonsense"
    assert catalogues.plural_count(po) == 2


def test_parse_rejects_garbage_and_accepts_empty():
    assert len(catalogues.parse(b"   ")) == 0
    with pytest.raises(catalogues.CatalogueError):
        catalogues.parse("garbage\n")


def test_new_catalogue_marks_broken_seed_translations_for_review():
    template = polib.POFile()
    template.append(_entry("Hello %(name)s."))
    base = polib.POFile()
    base.metadata["Plural-Forms"] = "nplurals=1; plural=0;"
    base.append(polib.POEntry(msgid="Hello %(name)s.", msgstr="Halo %(nama)s.", flags=["python-format"]))
    po = catalogues.new_catalogue(template, language_code="xx", base=base)
    assert po.metadata["Plural-Forms"] == "nplurals=1; plural=0;"
    assert po.find("Hello %(name)s.").fuzzy


def test_stats_and_percent():
    po = polib.POFile()
    assert catalogues.stats(po).percent == 100
    po.append(polib.POEntry(msgid="a", msgstr="A"))
    po.append(polib.POEntry(msgid="b", msgstr="B", flags=["fuzzy"]))
    po.append(polib.POEntry(msgid="c"))
    po.append(polib.POEntry(msgid="d", msgstr="D", obsolete=True))
    counts = catalogues.stats(po)
    assert (counts.total, counts.translated, counts.fuzzy, counts.untranslated, counts.percent) == (3, 1, 1, 1, 33)
