"""One interface for contributor files, whatever the backend.

Submissions, audio and translations store files through these functions
rather than calling a storage SDK. The backend (local filesystem or any
S3-compatible store) is chosen by ``STORAGE_BACKEND``; see
:mod:`baibu.core.storage_config`.

Records keep the returned *key* (a relative path such as
``submissions/raw/2026/10/06/<id>.json``), never a backend-specific URI, so
a deployment can move its files to another backend without rewriting rows.
"""

import json
import logging
from datetime import UTC
from datetime import datetime

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import Storage
from django.core.files.storage import storages

logger = logging.getLogger(__name__)

PRIVATE = "private"


class PrivateFileSystemStorage(FileSystemStorage):
    """Filesystem storage whose files have no URL."""

    def url(self, name):
        msg = "Private files are not served over HTTP."
        raise NotImplementedError(msg)


def private_storage() -> Storage:
    return storages[PRIVATE]


def build_key(area: str, name: str, *, now: datetime | None = None) -> str:
    """Return ``<area>/<yyyy>/<mm>/<dd>/<name>``.

    ``area`` is a path such as ``submissions/raw``; ``name`` should be unique,
    for example a record's UUID with an extension.
    """
    now = now or datetime.now(UTC)
    area = area.strip("/")
    if not area or not name or "/" in name or name in {".", ".."}:
        msg = f"Invalid storage key parts: area={area!r} name={name!r}"
        raise ValueError(msg)
    return f"{area}/{now:%Y/%m/%d}/{name}"


def save_bytes(key: str, data: bytes) -> str:
    """Store ``data`` under ``key`` and return the key actually used.

    If the key is already taken the backend picks a free variant, so always
    keep the returned value.
    """
    saved = private_storage().save(key, ContentFile(data))
    logger.info("Stored %d bytes at %s", len(data), saved)
    return saved


def save_json(key: str, payload: dict) -> str:
    return save_bytes(key, json.dumps(payload, ensure_ascii=False, indent=2).encode())


def read_bytes(key: str) -> bytes | None:
    """Return the file's contents, or ``None`` if there is no such file."""
    if not key:
        return None
    storage = private_storage()
    try:
        with storage.open(key, "rb") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def read_json(key: str) -> dict | None:
    data = read_bytes(key)
    return None if data is None else json.loads(data)


def exists(key: str) -> bool:
    return bool(key) and private_storage().exists(key)


def delete(key: str) -> bool:
    """Delete the file. Returns ``False`` if it was already gone."""
    if not exists(key):
        return False
    private_storage().delete(key)
    logger.info("Deleted %s", key)
    return True
