import pytest

from baibu.submissions import text


def test_normalise_tidies_spacing_and_line_breaks():
    raw = "  First   line\r\nsecond\tline \x00\x07\r\n\r\n\r\n\r\nThird  "
    assert text.normalise(raw) == "First line\nsecond line\n\nThird"


def test_normalise_composes_unicode():
    assert text.normalise("é") == "é"


def test_content_hash_ignores_spacing_only():
    assert text.content_hash("a  b\n c") == text.content_hash("a b c ")
    assert text.content_hash("a b c") != text.content_hash("a b d")


@pytest.mark.parametrize(
    ("raw", "expected", "kind"),
    [
        ("write to amina.k+test@example.org today", "write to [email] today", "email"),
        ("see https://example.org/page?x=1 and www.example.net", "see [link] and [link]", "link"),
        ("call +1 (555) 010-0199 now", "call [phone] now", "phone"),
        ("call 0812 3456 7890.", "call [phone].", "phone"),
    ],
)
def test_redact_replaces_personal_details(raw, expected, kind):
    result = text.redact(raw)
    assert result.text == expected
    assert result.counts[kind] >= 1


@pytest.mark.parametrize(
    "raw", ["In 2024 we planted 300 trees.", "Room 12-34", "version 1.2.3", "on 2026-10-06 at 10.30"]
)
def test_redact_leaves_short_numbers(raw):
    result = text.redact(raw)
    assert result.text == raw
    assert result.total == 0
