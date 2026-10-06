from unittest import mock

import pytest

from baibu.localization import extraction
from baibu.localization.extraction import SourceRoot


def test_extracts_templates_and_python(roots):
    template = extraction.extract(roots)
    by_id = {(entry.msgctxt, entry.msgid): entry for entry in template}
    assert (None, "Good morning, example friend") in by_id
    assert ("month name", "May") in by_id
    plural = by_id[(None, "%(count)s example basket")]
    assert plural.msgid_plural == "%(count)s example baskets"
    greeting = by_id[(None, "Welcome to the example market, %(name)s.")]
    assert "python-format" in greeting.flags
    # Template occurrences point at the template, not the converted file.
    assert by_id[(None, "Sign in")].occurrences == [("example/templates/page.html", "2")]
    assert template.metadata["Content-Type"] == "text/plain; charset=UTF-8"


def test_skips_tests_hidden_and_binary_files(tmp_path):
    for name in ("tests", ".hidden", "node_modules"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "skip.py").write_text('_("Skipped example")\n', encoding="utf-8")
    (tmp_path / "broken.html").write_bytes(b"\xff\xfe not text")
    (tmp_path / "kept.py").write_text('from django.utils.translation import gettext as _\n_("Kept example")\n')
    template = extraction.extract([SourceRoot(tmp_path, "t")])
    assert [entry.msgid for entry in template] == ["Kept example"]


def test_no_strings_gives_an_empty_template(tmp_path):
    assert len(extraction.extract([SourceRoot(tmp_path, "t")])) == 0


def test_default_roots_include_deployment_templates(settings, tmp_path):
    settings.DEPLOYMENT_DIR = tmp_path
    labels = [root.label for root in extraction.default_roots()]
    assert labels == ["baibu", "config"]
    (tmp_path / "templates").mkdir()
    labels = [root.label for root in extraction.default_roots()]
    assert labels == ["baibu", "config", "deployment/templates"]


def test_the_real_code_is_extracted():
    messages = {entry.msgid for entry in extraction.extract()}
    assert {"Your contributions", "Translations", "Sign in"} <= messages


def test_missing_xgettext_is_reported(roots):
    with (
        mock.patch("baibu.localization.extraction.shutil.which", return_value=None),
        pytest.raises(extraction.ExtractionError, match="xgettext was not found"),
    ):
        extraction.extract(roots)


def test_xgettext_failure_is_reported(roots):
    failed = mock.Mock(returncode=1, stderr="boom")
    with (
        mock.patch("baibu.localization.extraction.subprocess.run", return_value=failed),
        pytest.raises(extraction.ExtractionError, match="boom"),
    ):
        extraction.extract(roots)
