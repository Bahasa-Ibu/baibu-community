"""Loading published translations into running processes.

Published catalogues live in file storage, which every web and worker
process can reach. Each process copies the published ``.mo`` files into
``LOCALIZATION_PUBLISHED_DIR`` (listed first in ``LOCALE_PATHS``) and resets
Django's translation caches. A version marker in the cache (the id of the
newest publication) tells a process when to do this again; it checks at most
every ``LOCALIZATION_SYNC_SECONDS``, before a request is handled or a Celery
task runs.
"""

import gettext
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.utils.translation import to_locale
from django.utils.translation import trans_real

from baibu.core import storage

logger = logging.getLogger(__name__)

VERSION_CACHE_KEY = "localization:published-version"
NOTHING_PUBLISHED = "none"
MO_NAME = "django.mo"

_lock = threading.Lock()
_state = {"loaded": None, "checked_at": 0.0}


def published_dir() -> Path:
    return Path(settings.LOCALIZATION_PUBLISHED_DIR)


def published_version() -> str:
    """The id of the newest publication, from the cache or the database."""
    version = cache.get(VERSION_CACHE_KEY)
    if version is None:
        from .models import TranslationPublication

        newest = TranslationPublication.objects.order_by("-published_at", "-id").values_list("id", flat=True).first()
        version = str(newest) if newest else NOTHING_PUBLISHED
        cache.set(VERSION_CACHE_KEY, version, timeout=None)
    return version


def announce(version: str) -> None:
    """Tell every process that a new publication exists."""
    cache.set(VERSION_CACHE_KEY, version, timeout=None)


def reset_translation_caches() -> None:
    """Make Django read the catalogue files again.

    Clears what Django's own autoreloader clears when a .mo file changes,
    plus the language-availability caches, so a language whose first
    catalogue was just published becomes available. The active translation
    of other threads is left alone; each request activates its language
    again through LocaleMiddleware.
    """
    gettext._translations.clear()
    trans_real._translations = {}
    trans_real._default = None
    trans_real.check_for_language.cache_clear()
    trans_real.get_languages.cache_clear()
    trans_real.get_supported_language_variant.cache_clear()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".mo")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def materialise() -> bool:
    """Copy the newest publication of each language into the published directory.

    Returns ``False`` if a file could not be read from storage (the next
    check tries again).
    """
    from .models import TranslationPublication
    from .services import translatable_languages

    codes = [code for code, _name in translatable_languages()]
    newest = (
        TranslationPublication.objects.filter(language_code__in=codes)
        .order_by("language_code", "-version")
        .distinct("language_code")
    )
    root = published_dir()
    wanted: set[Path] = set()
    complete = True
    for publication in newest:
        target = root / to_locale(publication.language_code) / "LC_MESSAGES" / MO_NAME
        wanted.add(target)
        data = storage.read_bytes(publication.mo_key)
        if data is None:
            logger.error("Published translations %s are missing from storage (%s)", publication, publication.mo_key)
            complete = False
            continue
        if not target.exists() or target.read_bytes() != data:
            _write_atomic(target, data)
    if root.is_dir():
        for stale in root.glob(f"*/LC_MESSAGES/{MO_NAME}"):
            if stale not in wanted:
                stale.unlink(missing_ok=True)
    return complete


def sync(*, force: bool = False) -> bool:
    """Load newly published translations into this process. Returns whether it reloaded."""
    with _lock:
        _state["checked_at"] = time.monotonic()
        version = published_version()
        if not force and version == _state["loaded"]:
            return False
        complete = materialise()
        reset_translation_caches()
        _state["loaded"] = version if complete else None
        logger.info("Loaded published translations (version %s)", version)
        return True


def sync_if_due() -> None:
    """Called before each request and task; cheap unless a check is due."""
    if not settings.LOCALIZATION_SYNC:
        return
    checked_at = _state["checked_at"]
    if checked_at and time.monotonic() - checked_at < settings.LOCALIZATION_SYNC_SECONDS:
        return
    try:
        sync()
    except Exception:
        # Translations must never take a page or a task down.
        logger.exception("Could not load published translations")


def sync_before_task(**kwargs) -> None:
    sync_if_due()


def forget() -> None:
    """Forget what this process loaded (used by tests)."""
    _state["loaded"] = None
    _state["checked_at"] = 0.0
