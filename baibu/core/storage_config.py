"""Build the ``STORAGES`` setting from the environment.

Kept free of Django imports so the settings module can call it.

Two file stores are configured besides static files:

- ``default``: ordinary uploads (Django's ``MEDIA``).
- ``private``: contributor files (submitted text, audio, translations). They
  are never given a public URL; code reads them through
  :mod:`baibu.core.storage`.

With ``STORAGE_BACKEND=local`` both live on the local filesystem. With
``STORAGE_BACKEND=s3`` both live in one bucket on any S3-compatible server,
under the ``media/`` and ``private/`` prefixes.
"""

from dataclasses import dataclass

STORAGE_BACKENDS = ("local", "s3")


class StorageConfigError(ValueError):
    """Raised when the storage settings are incomplete or contradictory."""


@dataclass(frozen=True)
class S3Options:
    bucket: str = ""
    endpoint_url: str = ""
    region: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    addressing_style: str = "path"
    signed_url_seconds: int = 3600


def build_storages(
    backend: str,
    *,
    media_root: str,
    private_root: str,
    s3: S3Options | None = None,
    staticfiles_backend: str = "django.contrib.staticfiles.storage.StaticFilesStorage",
) -> dict:
    staticfiles = {"BACKEND": staticfiles_backend}
    if backend == "local":
        return {
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": media_root},
            },
            "private": {
                "BACKEND": "baibu.core.storage.PrivateFileSystemStorage",
                "OPTIONS": {"location": private_root},
            },
            "staticfiles": staticfiles,
        }
    if backend == "s3":
        s3 = s3 or S3Options()
        if not s3.bucket:
            msg = "STORAGE_BACKEND=s3 needs S3_BUCKET."
            raise StorageConfigError(msg)
        options = {
            "bucket_name": s3.bucket,
            "endpoint_url": s3.endpoint_url or None,
            "region_name": s3.region or None,
            "access_key": s3.access_key_id or None,
            "secret_key": s3.secret_access_key or None,
            "addressing_style": s3.addressing_style or None,
            # Objects inherit the bucket's access policy; nothing is made public.
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": s3.signed_url_seconds,
            # Never silently rename: callers choose unique keys.
            "file_overwrite": False,
        }
        return {
            "default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {**options, "location": "media"}},
            "private": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {**options, "location": "private"}},
            "staticfiles": staticfiles,
        }
    msg = f"Unknown STORAGE_BACKEND {backend!r}; expected one of {', '.join(STORAGE_BACKENDS)}."
    raise StorageConfigError(msg)
