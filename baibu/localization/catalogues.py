"""Working with gettext catalogues (.po/.pot/.mo) through polib.

Pure functions: nothing here touches the database or file storage.
"""

import gettext
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import django
import polib
from django.utils.translation import gettext as _
from django.utils.translation import to_locale

DEFAULT_PLURAL_FORMS = "nplurals=2; plural=(n != 1);"
MAX_PLURALS = 6
PLURAL_FORMS_RE = re.compile(r"^\s*nplurals\s*=\s*(?P<n>\d+)\s*;\s*plural\s*=\s*(?P<expr>[^;]+?)\s*;?\s*$")
# printf-style conversions as Python's % operator understands them.
PRINTF_RE = re.compile(r"%(?:\((?P<name>[^)]*)\))?[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?(?P<type>.)", re.DOTALL)
PRINTF_TYPES = set("diouxXeEfFgGcrsa%")


class CatalogueError(ValueError):
    """A catalogue or a value for it is not valid."""


@dataclass(frozen=True)
class Stats:
    total: int
    translated: int
    fuzzy: int

    @property
    def untranslated(self) -> int:
        return self.total - self.translated - self.fuzzy

    @property
    def percent(self) -> int:
        return round(100 * self.translated / self.total) if self.total else 100


def parse(data: bytes | str) -> polib.POFile:
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    if not text.strip():
        return polib.POFile()
    try:
        return polib.pofile(text)
    except (OSError, ValueError) as exc:
        msg = _("Not a valid PO file: %(error)s") % {"error": exc}
        raise CatalogueError(msg) from exc


def dump(po: polib.POFile) -> bytes:
    return str(po).encode("utf-8")


def compile_mo(po: polib.POFile) -> bytes:
    """Compile to the binary .mo format. Only translated, non-fuzzy entries are included."""
    return po.to_binary()


def entry_key(entry: polib.POEntry) -> str:
    """A stable identifier for an entry (context, message and plural)."""
    raw = "\x04".join((entry.msgctxt or "", entry.msgid, entry.msgid_plural or ""))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def active_entries(po: polib.POFile) -> list[polib.POEntry]:
    return [entry for entry in po if not entry.obsolete]


def entry_state(entry: polib.POEntry) -> str:
    if entry.fuzzy:
        return "fuzzy"
    return "translated" if entry.translated() else "untranslated"


def stats(po: polib.POFile) -> Stats:
    entries = active_entries(po)
    return Stats(
        total=len(entries),
        translated=sum(1 for entry in entries if entry.translated()),
        fuzzy=sum(1 for entry in entries if entry.fuzzy),
    )


def content_hash(po: polib.POFile) -> str:
    """Hash of the entries (not the header), to tell whether a template changed."""
    digest = hashlib.sha256()
    for entry in po:
        digest.update(repr((entry.msgctxt, entry.msgid, entry.msgid_plural, entry.occurrences)).encode())
        digest.update(repr((sorted(entry.flags), entry.comment)).encode())
    return digest.hexdigest()


# Plural forms ------------------------------------------------------------------


def parse_plural_forms(value: str) -> tuple[int, str]:
    """Validate a ``Plural-Forms`` header and return ``(nplurals, expression)``."""
    match = PLURAL_FORMS_RE.match(value or "")
    if not match:
        msg = _("Plural forms must look like “nplurals=2; plural=(n != 1);”.")
        raise CatalogueError(msg)
    count = int(match["n"])
    if not 1 <= count <= MAX_PLURALS:
        msg = _("The number of plural forms must be between 1 and %(max)d.") % {"max": MAX_PLURALS}
        raise CatalogueError(msg)
    expression = match["expr"]
    try:
        gettext.c2py(expression)
    except (ValueError, RecursionError) as exc:
        msg = _("The plural expression is not valid: %(error)s") % {"error": exc}
        raise CatalogueError(msg) from exc
    return count, expression


def plural_forms(po: polib.POFile) -> str:
    return po.metadata.get("Plural-Forms") or DEFAULT_PLURAL_FORMS


def plural_count(po: polib.POFile) -> int:
    try:
        return parse_plural_forms(plural_forms(po))[0]
    except CatalogueError:
        return 2


def plural_examples(value: str, *, limit: int = 3) -> list[list[int]]:
    """For each plural form, a few numbers that use it (to label the fields)."""
    count, expression = parse_plural_forms(value)
    function = gettext.c2py(expression)
    examples: list[list[int]] = [[] for _index in range(count)]
    for number in range(1000):
        index = function(number)
        if 0 <= index < count and len(examples[index]) < limit:
            examples[index].append(number)
    return examples


def known_plural_forms(language_code: str) -> str | None:
    """The plural forms Django's own catalogue uses for the language, if it has one."""
    path = Path(django.__file__).parent / "conf" / "locale" / to_locale(language_code) / "LC_MESSAGES" / "django.po"
    if not path.exists():
        return None
    value = polib.pofile(str(path)).metadata.get("Plural-Forms")
    try:
        parse_plural_forms(value)
    except CatalogueError:
        return None
    return value


def normalise_plurals(po: polib.POFile) -> None:
    """Give every plural entry exactly one translation slot per plural form."""
    count = plural_count(po)
    for entry in po:
        if not entry.msgid_plural:
            continue
        entry.msgstr_plural = {index: entry.msgstr_plural.get(index, "") for index in range(count)}


def set_header(po: polib.POFile, *, language_code: str, plural_forms_value: str) -> None:
    po.metadata.update(
        {
            "Project-Id-Version": po.metadata.get("Project-Id-Version") or "interface",
            "Language": to_locale(language_code),
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
            "Plural-Forms": plural_forms_value,
        }
    )
    normalise_plurals(po)


# Building and merging ------------------------------------------------------------


def new_catalogue(template: polib.POFile, *, language_code: str, base: polib.POFile | None = None) -> polib.POFile:
    """A catalogue for ``language_code`` with the template's entries.

    Translations in ``base`` (for example a deployment's existing .po file)
    are kept where the message still exists.
    """
    po = base if base is not None else polib.POFile()
    po.merge(template)
    value = (base.metadata.get("Plural-Forms") if base is not None else None) or known_plural_forms(language_code)
    try:
        parse_plural_forms(value)
    except CatalogueError:
        value = DEFAULT_PLURAL_FORMS
    set_header(po, language_code=language_code, plural_forms_value=value)
    for entry in active_entries(po):
        if entry.translated() and placeholder_problem(entry, entry.msgstr, *entry.msgstr_plural.values()):
            entry.fuzzy = True
    return po


def merge_template(po: polib.POFile, template: polib.POFile) -> polib.POFile:
    """Bring a catalogue up to date with a new template, keeping translations.

    Messages no longer in the code become obsolete (kept in the file, never
    shown or compiled), so their translations return if the message does.
    """
    po.merge(template)
    normalise_plurals(po)
    return po


def find_entry(po: polib.POFile, key: str) -> polib.POEntry | None:
    for entry in active_entries(po):
        if entry_key(entry) == key:
            return entry
    return None


# Validation -----------------------------------------------------------------------


def _placeholders(text: str) -> tuple[set[str], int, bool]:
    """Named placeholders, count of unnamed ones, and whether a stray % was found."""
    named: set[str] = set()
    unnamed = 0
    stray = False
    for match in PRINTF_RE.finditer(text):
        if match["type"] not in PRINTF_TYPES:
            stray = True
        elif match["type"] == "%":
            stray = stray or match.group(0) != "%%"
        elif match["name"] is not None:
            named.add(match["name"])
        else:
            unnamed += 1
    if text.count("%") > sum(m.group(0).count("%") for m in PRINTF_RE.finditer(text)):
        stray = True
    return named, unnamed, stray


def placeholder_problem(entry: polib.POEntry, *translations: str) -> str | None:
    """Return a message if a translation would break the format string, else ``None``.

    Only entries flagged ``python-format`` are checked: their translation may
    use the same named placeholders (``%(name)s``) as the original, in any
    order, and must keep the same number of unnamed ones (``%s``).
    """
    if "python-format" not in entry.flags:
        return None
    sources = [entry.msgid] + ([entry.msgid_plural] if entry.msgid_plural else [])
    allowed: set[str] = set()
    unnamed_counts: set[int] = set()
    for source in sources:
        named, unnamed, _stray = _placeholders(source)
        allowed |= named
        unnamed_counts.add(unnamed)
    for text in translations:
        if not text:
            continue
        named, unnamed, stray = _placeholders(text)
        if stray:
            return _("Write a percent sign as %(sign)s.") % {"sign": "%%"}
        if unknown := named - allowed:
            names = ", ".join(f"%({name})s" for name in sorted(unknown))
            return _("Unknown placeholder: %(names)s. Use only the placeholders in the original.") % {"names": names}
        if unnamed not in unnamed_counts:
            return _("Keep the same number of %(placeholder)s placeholders as the original.") % {"placeholder": "%s"}
    return None
