# File storage

Contributor files (submitted text, audio, translations) are stored through
one small interface, `baibu.core.storage`. Feature code never calls a storage
SDK directly, so the same code runs on a laptop and on any S3-compatible
object store.

## Two stores

| Store | Holds | Served over HTTP |
| --- | --- | --- |
| `default` | Ordinary uploads (Django's media files) | Yes, under `MEDIA_URL` |
| `private` | Contributor files | No. On the filesystem they have no URL; on S3, only short-lived signed URLs |

Both are entries in Django's `STORAGES` setting, built by
`baibu.core.storage_config.build_storages()` from the environment.

## Backends

**`STORAGE_BACKEND=local`** (default). Files are written under
`DJANGO_MEDIA_ROOT` and `DJANGO_PRIVATE_MEDIA_ROOT`. Back these directories
up with the database.

**`STORAGE_BACKEND=s3`**. Both stores use one bucket, under the `media/` and
`private/` prefixes, on any server that speaks the S3 API: a self-hosted
open-source server or a hosted service. Set `S3_BUCKET` and, for anything
other than the default endpoint, `S3_ENDPOINT_URL`. Credentials left empty
are resolved the usual way (environment, instance role). Objects are
written without an ACL, so they follow the bucket's policy: keep the bucket
private.

To try the S3 backend locally, start the optional SeaweedFS service and
point the app at it:

```sh
docker compose --profile s3 up -d s3
# in .env
STORAGE_BACKEND=s3
S3_BUCKET=platform-files
S3_ENDPOINT_URL=http://s3:8333
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=local
S3_SECRET_ACCESS_KEY=local
```

Create the bucket once, for example from `docker compose run --rm django
python manage.py shell` with boto3.

## The interface

```python
from baibu.core import storage

key = storage.build_key("submissions/raw", f"{submission.id}.json")
key = storage.save_json(key, {"text": "..."})  # keep the returned key
payload = storage.read_json(key)                # None if missing
storage.delete(key)                             # False if already gone
```

`save_bytes`, `read_bytes` and `exists` work the same way for binary files.

Records store the **key** (a relative path such as
`submissions/raw/2026/10/06/<id>.json`), not a backend URI, so a deployment
can move its files to another backend by copying them, without rewriting
database rows. Keys are never overwritten: if a key is taken, the backend
picks a free variant and returns it.

## Tests

Tests use in-memory storage. `baibu/core/tests/test_storage.py` runs the
same cases against memory, a temporary directory and, when
`S3_TEST_ENDPOINT_URL` is set, a real S3-compatible server. CI starts
SeaweedFS for this; locally:

```sh
docker compose --profile s3 up -d s3
docker compose run --rm -e S3_TEST_ENDPOINT_URL=http://s3:8333 django pytest baibu/core/tests/test_storage.py
```
