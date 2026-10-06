"""The translation workflow: source strings, drafts, publishing and restoring.

Files (templates, drafts, published catalogues) are stored through
:mod:`baibu.core.storage`; the database keeps their keys and the audit trail.
Storage keys are never overwritten, so saving a draft writes a new file and
removes the previous one once the database change is committed.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import polib
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import to_locale

from baibu.core import storage

from . import catalogues
from . import extraction
from . import runtime
from .models import TranslationCatalogue
from .models import TranslationPublication
from .models import TranslationSource

logger = logging.getLogger(__name__)

SOURCE_LANGUAGE = "en"
AREA = "translations"


class NoSourceError(Exception):
    """Source strings have not been extracted yet."""


class UnknownLanguageError(LookupError):
    """The language is not one this deployment translates."""


@dataclass
class SourceUpdate:
    source: TranslationSource
    created: bool
    merged: list[str] = field(default_factory=list)


@dataclass
class Edit:
    """A translator's change to one entry."""

    key: str
    # One value for an ordinary entry; one per plural form otherwise.
    values: list[str]
    fuzzy: bool
    # Fingerprint of the entry as the translator saw it (see ``fingerprint``).
    seen: str


@dataclass
class SaveResult:
    changed: int = 0
    conflicts: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def translatable_languages() -> list[tuple[str, str]]:
    """The deployment's languages other than the source language (English)."""
    return [(code, name) for code, name in settings.LANGUAGES if code != SOURCE_LANGUAGE]


def check_language(language_code: str) -> None:
    if language_code not in dict(translatable_languages()):
        raise UnknownLanguageError(language_code)


def latest_source() -> TranslationSource | None:
    return TranslationSource.objects.order_by("-created_at").first()


def _read_po(key: str) -> polib.POFile:
    data = storage.read_bytes(key)
    if data is None:
        msg = f"Stored catalogue {key} is missing."
        raise FileNotFoundError(msg)
    return catalogues.parse(data)


def read_template(source: TranslationSource) -> polib.POFile:
    return _read_po(source.pot_key)


def read_draft(catalogue: TranslationCatalogue) -> polib.POFile:
    return _read_po(catalogue.draft_key)


def _save_draft(catalogue: TranslationCatalogue, po: polib.POFile, *, user=None, source=None) -> None:
    """Store ``po`` as the catalogue's draft and update the row (inside a transaction)."""
    old_key = catalogue.draft_key
    new_key = storage.save_bytes(
        storage.build_key(f"{AREA}/{catalogue.language_code}/drafts", f"{uuid.uuid7()}.po"), catalogues.dump(po)
    )
    catalogue.draft_key = new_key
    catalogue.updated_at = timezone.now()
    catalogue.updated_by = user
    if source is not None:
        catalogue.source = source
    try:
        catalogue.save()
    except Exception:
        storage.delete(new_key)
        raise
    if old_key and old_key != new_key:
        transaction.on_commit(lambda: storage.delete(old_key))


# Source strings --------------------------------------------------------------------


def update_sources(*, user=None, roots=None, force: bool = False) -> SourceUpdate:
    """Extract the interface strings from the code and merge them into every draft.

    An extraction identical to the current template is not stored again
    (unless ``force``), but drafts that are behind are still brought up to date.
    """
    template = extraction.extract(roots)
    digest = catalogues.content_hash(template)
    current = latest_source()
    created = force or current is None or current.content_hash != digest
    with transaction.atomic():
        if created:
            source_id = uuid.uuid7()
            key = storage.save_bytes(
                storage.build_key(f"{AREA}/sources", f"{source_id}.pot"), catalogues.dump(template)
            )
            try:
                current = TranslationSource.objects.create(
                    id=source_id,
                    pot_key=key,
                    content_hash=digest,
                    entry_count=len(template),
                    created_by=user,
                )
            except Exception:
                storage.delete(key)
                raise
        merged = [
            code
            for code, _name in translatable_languages()
            if _bring_up_to_date(code, current, template=template, user=user)
        ]
    logger.info("Source strings %s (%d entries); drafts updated: %s", current.pk, len(template), merged or "none")
    return SourceUpdate(source=current, created=created, merged=merged)


def _deployment_catalogue(language_code: str) -> polib.POFile | None:
    """The deployment's own .po file for the language, if it has one."""
    path = Path(settings.DEPLOYMENT_DIR) / "locale" / to_locale(language_code) / "LC_MESSAGES" / "django.po"
    if not path.is_file():
        return None
    try:
        return catalogues.parse(path.read_bytes())
    except catalogues.CatalogueError:
        logger.warning("Ignoring %s: not a valid PO file", path)
        return None


def _bring_up_to_date(language_code: str, source: TranslationSource, *, template=None, user=None) -> bool:
    """Create the language's draft, or merge a newer template into it. Returns whether it changed."""
    catalogue = TranslationCatalogue.objects.select_for_update().filter(language_code=language_code).first()
    if catalogue is not None and catalogue.source_id == source.pk:
        return False
    template = template if template is not None else read_template(source)
    if catalogue is None:
        po = catalogues.new_catalogue(template, language_code=language_code, base=_deployment_catalogue(language_code))
        catalogue = TranslationCatalogue(language_code=language_code)
    else:
        po = catalogues.merge_template(read_draft(catalogue), template)
    _save_draft(catalogue, po, user=user, source=source)
    return True


def get_catalogue(language_code: str, *, user=None) -> TranslationCatalogue:
    """The language's catalogue, created or brought up to date with the newest template."""
    check_language(language_code)
    source = latest_source()
    if source is None:
        raise NoSourceError
    with transaction.atomic():
        _bring_up_to_date(language_code, source, user=user)
        return TranslationCatalogue.objects.get(language_code=language_code)


# Editing ---------------------------------------------------------------------------


def fingerprint(entry: polib.POEntry) -> str:
    """A short digest of an entry's translation, to detect someone else's change."""
    return hashlib.sha256(repr((_values(entry), entry.fuzzy)).encode()).hexdigest()[:16]


def _values(entry: polib.POEntry) -> list[str]:
    if entry.msgid_plural:
        return [entry.msgstr_plural[index] for index in sorted(entry.msgstr_plural)]
    return [entry.msgstr]


def _apply(entry: polib.POEntry, edit: Edit) -> bool:
    """Apply an edit to an entry. Returns whether anything changed."""
    before = fingerprint(entry)
    if entry.msgid_plural:
        for index in sorted(entry.msgstr_plural):
            entry.msgstr_plural[index] = edit.values[index] if index < len(edit.values) else ""
    else:
        entry.msgstr = edit.values[0] if edit.values else ""
    entry.fuzzy = edit.fuzzy and bool(any(edit.values))
    if not entry.fuzzy:
        entry.previous_msgid = entry.previous_msgid_plural = entry.previous_msgctxt = None
    return fingerprint(entry) != before


def save_entries(language_code: str, edits: list[Edit], *, user) -> SaveResult:
    """Apply translators' edits to the draft.

    Entries someone else changed since the page was loaded are not
    overwritten (reported in ``conflicts``); translations that would break a
    format string are refused (reported in ``errors``).
    """
    check_language(language_code)
    result = SaveResult()
    with transaction.atomic():
        catalogue = TranslationCatalogue.objects.select_for_update().get(language_code=language_code)
        po = read_draft(catalogue)
        for edit in edits:
            entry = catalogues.find_entry(po, edit.key)
            if entry is None:
                result.conflicts.append(edit.key)
                continue
            values = [value.replace("\r\n", "\n") for value in edit.values]
            if values == _values(entry) and edit.fuzzy == entry.fuzzy:
                continue
            if fingerprint(entry) != edit.seen:
                result.conflicts.append(edit.key)
                continue
            if problem := catalogues.placeholder_problem(entry, *values):
                result.errors[edit.key] = problem
                continue
            if _apply(entry, Edit(edit.key, values, edit.fuzzy, edit.seen)):
                result.changed += 1
        if result.changed:
            _save_draft(catalogue, po, user=user)
    return result


def set_plural_forms(language_code: str, value: str, *, user) -> None:
    catalogues.parse_plural_forms(value)
    check_language(language_code)
    with transaction.atomic():
        catalogue = TranslationCatalogue.objects.select_for_update().get(language_code=language_code)
        po = read_draft(catalogue)
        catalogues.set_header(po, language_code=language_code, plural_forms_value=value.strip())
        _save_draft(catalogue, po, user=user)


def import_catalogue(language_code: str, data: bytes, *, user) -> SaveResult:
    """Take translations from an uploaded .po file for messages the draft has.

    Messages not in the draft are ignored; translations that would break a
    format string are skipped.
    """
    check_language(language_code)
    uploaded = catalogues.parse(data)
    result = SaveResult()
    with transaction.atomic():
        catalogue = TranslationCatalogue.objects.select_for_update().get(language_code=language_code)
        po = read_draft(catalogue)
        count = catalogues.plural_count(po)
        by_key = {catalogues.entry_key(entry): entry for entry in catalogues.active_entries(po)}
        for incoming in catalogues.active_entries(uploaded):
            key = catalogues.entry_key(incoming)
            entry = by_key.get(key)
            if entry is None or not (incoming.msgstr or any(incoming.msgstr_plural.values())):
                continue
            if entry.msgid_plural:
                values = [incoming.msgstr_plural.get(index, "") for index in range(count)]
            else:
                values = [incoming.msgstr]
            if problem := catalogues.placeholder_problem(entry, *values):
                result.errors[key] = problem
                continue
            if _apply(entry, Edit(key, values, incoming.fuzzy, "")):
                result.changed += 1
        if result.changed:
            _save_draft(catalogue, po, user=user)
    return result


# Publishing ------------------------------------------------------------------------


def latest_publication(language_code: str) -> TranslationPublication | None:
    return TranslationPublication.objects.filter(language_code=language_code).order_by("-version").first()


def _next_version(language_code: str) -> int:
    return (
        TranslationPublication.objects.filter(language_code=language_code).aggregate(v=Max("version"))["v"] or 0
    ) + 1


def _after_publish(publication: TranslationPublication) -> None:
    def announce_and_load():
        runtime.announce(str(publication.pk))
        if settings.LOCALIZATION_SYNC:
            runtime.sync()

    transaction.on_commit(announce_and_load)


def publish(language_code: str, *, user) -> TranslationPublication:
    """Compile the draft and make it the language's live translations."""
    check_language(language_code)
    with transaction.atomic():
        catalogue = TranslationCatalogue.objects.select_for_update().get(language_code=language_code)
        po = read_draft(catalogue)
        counts = catalogues.stats(po)
        publication_id = uuid.uuid7()
        area = f"{AREA}/{language_code}/published"
        po_key = storage.save_bytes(storage.build_key(area, f"{publication_id}.po"), catalogues.dump(po))
        mo_key = storage.save_bytes(storage.build_key(area, f"{publication_id}.mo"), catalogues.compile_mo(po))
        try:
            publication = TranslationPublication.objects.create(
                id=publication_id,
                language_code=language_code,
                version=_next_version(language_code),
                po_key=po_key,
                mo_key=mo_key,
                total_count=counts.total,
                translated_count=counts.translated,
                fuzzy_count=counts.fuzzy,
                published_by=user,
            )
        except Exception:
            storage.delete(po_key)
            storage.delete(mo_key)
            raise
        _after_publish(publication)
    logger.info("Published %s by %s", publication, getattr(user, "pk", None))
    return publication


def restore(publication: TranslationPublication, *, user) -> TranslationPublication:
    """Make an earlier publication live again, as a new version. The draft is not changed."""
    check_language(publication.language_code)
    with transaction.atomic():
        # Serialise with other publications of the same language.
        TranslationCatalogue.objects.select_for_update().filter(language_code=publication.language_code).first()
        restored = TranslationPublication.objects.create(
            language_code=publication.language_code,
            version=_next_version(publication.language_code),
            po_key=publication.po_key,
            mo_key=publication.mo_key,
            total_count=publication.total_count,
            translated_count=publication.translated_count,
            fuzzy_count=publication.fuzzy_count,
            restored_from=publication,
            published_by=user,
        )
        _after_publish(restored)
    logger.info("Restored %s as %s by %s", publication, restored, getattr(user, "pk", None))
    return restored


def _translations(po: polib.POFile) -> set:
    return {
        (catalogues.entry_key(entry), tuple(_values(entry)), entry.fuzzy) for entry in catalogues.active_entries(po)
    } | {("Plural-Forms", catalogues.plural_forms(po))}


def has_unpublished_changes(draft: polib.POFile, publication: TranslationPublication | None) -> bool:
    """Whether the draft's translations differ from what is live."""
    if publication is None:
        return True
    data = storage.read_bytes(publication.po_key)
    return data is None or _translations(draft) != _translations(catalogues.parse(data))
