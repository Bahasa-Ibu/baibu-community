"""Text normalisation and rule-based redaction.

These rules run on every submission before any model sees it, so a
deployment without a model still gets consistent text and basic redaction.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field

_LINE_BREAKS = re.compile(r"\r\n?|[\u2028\u2029]")
_SPACES = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_WHITESPACE = re.compile(r"\s+")

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
# Nine or more digits, optionally with a leading + and separators. Shorter
# runs (years, dates, prices) are left alone.
_PHONE = re.compile(r"(?<![\w+])\+?\d(?:[\s().-]{0,2}\d){8,}(?!\w)")

REDACTIONS = (("email", _EMAIL, "[email]"), ("link", _URL, "[link]"), ("phone", _PHONE, "[phone]"))


def normalise(text: str) -> str:
    """NFC, Unix line breaks, no control characters, tidy spacing."""
    text = unicodedata.normalize("NFC", text or "")
    text = _LINE_BREAKS.sub("\n", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def content_hash(text: str) -> str:
    """Hash that ignores differences in spacing, for duplicate detection."""
    collapsed = _WHITESPACE.sub(" ", normalise(text)).strip()
    return hashlib.sha256(collapsed.encode()).hexdigest()


def word_count(text: str) -> int:
    return len(text.split())


@dataclass
class Redacted:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> Redacted:
    """Replace email addresses, links and phone numbers with placeholders."""
    counts = {}
    for kind, pattern, placeholder in REDACTIONS:
        text, n = pattern.subn(placeholder, text)
        if n:
            counts[kind] = n
    return Redacted(text=text, counts=counts)
