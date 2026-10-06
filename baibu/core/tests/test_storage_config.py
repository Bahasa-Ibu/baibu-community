import pytest

from baibu.core.storage_config import S3Options
from baibu.core.storage_config import StorageConfigError
from baibu.core.storage_config import build_storages


def test_local_backend_keeps_media_and_private_files_apart():
    storages = build_storages("local", media_root="/srv/media", private_root="/srv/private")
    assert storages["default"]["OPTIONS"]["location"] == "/srv/media"
    assert storages["private"]["BACKEND"] == "baibu.core.storage.PrivateFileSystemStorage"
    assert storages["private"]["OPTIONS"]["location"] == "/srv/private"
    assert storages["staticfiles"]["BACKEND"] == "django.contrib.staticfiles.storage.StaticFilesStorage"


def test_s3_backend_uses_one_bucket_with_two_prefixes():
    s3 = S3Options(bucket="platform-files", endpoint_url="http://s3.example.org:8333", access_key_id="key")
    storages = build_storages("s3", media_root="", private_root="", s3=s3)
    media, private = storages["default"]["OPTIONS"], storages["private"]["OPTIONS"]
    assert storages["private"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert (media["location"], private["location"]) == ("media", "private")
    assert private["bucket_name"] == "platform-files"
    assert private["endpoint_url"] == "http://s3.example.org:8333"
    # Unset options fall back to the SDK's own resolution (environment, instance role).
    assert private["region_name"] is None
    assert private["secret_key"] is None
    # Nothing is published and nothing is silently overwritten.
    assert private["default_acl"] is None
    assert private["querystring_auth"] is True
    assert private["file_overwrite"] is False


def test_s3_backend_needs_a_bucket():
    with pytest.raises(StorageConfigError, match="S3_BUCKET"):
        build_storages("s3", media_root="", private_root="")


def test_unknown_backend_is_rejected():
    with pytest.raises(StorageConfigError, match="Unknown STORAGE_BACKEND"):
        build_storages("ftp", media_root="", private_root="")


def test_staticfiles_backend_can_be_replaced():
    storages = build_storages("local", media_root="", private_root="", staticfiles_backend="example.Static")
    assert storages["staticfiles"] == {"BACKEND": "example.Static"}
