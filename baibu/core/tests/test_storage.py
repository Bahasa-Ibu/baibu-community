"""The storage interface behaves the same on every backend.

The S3 cases run only when ``S3_TEST_ENDPOINT_URL`` points at an
S3-compatible server (CI starts one); elsewhere they are skipped.
"""

import os
import uuid
from datetime import UTC
from datetime import datetime

import pytest

from baibu.core import storage
from baibu.core.storage_config import S3Options
from baibu.core.storage_config import build_storages

S3_ENDPOINT = os.environ.get("S3_TEST_ENDPOINT_URL", "")


def _s3_storages():
    import boto3

    bucket = f"test-{uuid.uuid4().hex[:12]}"
    options = S3Options(
        bucket=bucket,
        endpoint_url=S3_ENDPOINT,
        region="us-east-1",
        access_key_id=os.environ.get("S3_TEST_ACCESS_KEY_ID", "test"),
        secret_access_key=os.environ.get("S3_TEST_SECRET_ACCESS_KEY", "test"),
    )
    boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        region_name=options.region,
        aws_access_key_id=options.access_key_id,
        aws_secret_access_key=options.secret_access_key,
    ).create_bucket(Bucket=bucket)
    return build_storages("s3", media_root="", private_root="", s3=options)


@pytest.fixture(
    params=[
        "memory",
        "filesystem",
        pytest.param("s3", marks=pytest.mark.skipif(not S3_ENDPOINT, reason="S3_TEST_ENDPOINT_URL not set")),
    ]
)
def backend(request, settings, tmp_path):
    if request.param == "filesystem":
        settings.STORAGES = build_storages("local", media_root=str(tmp_path / "m"), private_root=str(tmp_path / "p"))
    elif request.param == "s3":
        settings.STORAGES = _s3_storages()
    return request.param


def test_bytes_round_trip(backend):
    key = storage.save_bytes("audio/2026/10/06/clip.ogg", b"\x00\x01binary")
    assert key == "audio/2026/10/06/clip.ogg"
    assert storage.exists(key)
    assert storage.read_bytes(key) == b"\x00\x01binary"


def test_json_round_trip_keeps_unicode(backend):
    payload = {"text": "Ẹ ku àárọ̀, ꦲꦤꦏ꧀", "words": 3}
    key = storage.save_json("submissions/raw/2026/10/06/a.json", payload)
    assert storage.read_json(key) == payload
    assert "ꦲꦤꦏ꧀".encode() in storage.read_bytes(key)


def test_taken_key_is_not_overwritten(backend):
    first = storage.save_bytes("notes/2026/10/06/n.txt", b"first")
    second = storage.save_bytes("notes/2026/10/06/n.txt", b"second")
    assert first != second
    assert storage.read_bytes(first) == b"first"
    assert storage.read_bytes(second) == b"second"


def test_missing_file_reads_as_none(backend):
    assert storage.read_bytes("nothing/here.json") is None
    assert storage.read_json("nothing/here.json") is None
    assert storage.read_bytes("") is None
    assert not storage.exists("")


def test_delete(backend):
    key = storage.save_bytes("tmp/2026/10/06/x.bin", b"x")
    assert storage.delete(key) is True
    assert not storage.exists(key)
    assert storage.read_bytes(key) is None
    assert storage.delete(key) is False


def test_private_files_on_disk_have_no_url(settings, tmp_path):
    settings.STORAGES = build_storages("local", media_root=str(tmp_path / "m"), private_root=str(tmp_path / "p"))
    key = storage.save_bytes("a/b.txt", b"x")
    assert (tmp_path / "p" / "a" / "b.txt").read_bytes() == b"x"
    with pytest.raises(NotImplementedError):
        storage.private_storage().url(key)


def test_build_key_dates_the_path():
    when = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    assert storage.build_key("/submissions/raw/", "abc.json", now=when) == "submissions/raw/2026/01/02/abc.json"
    assert storage.build_key("audio", "x.ogg").startswith(f"audio/{datetime.now(UTC):%Y/%m/%d}/")


@pytest.mark.parametrize(("area", "name"), [("", "a.json"), ("raw", ""), ("raw", "../a.json"), ("raw", "..")])
def test_build_key_rejects_unsafe_parts(area, name):
    with pytest.raises(ValueError, match="Invalid storage key"):
        storage.build_key(area, name)
