import pytest

from baibu.users.models import User
from baibu.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath
    # A fresh in-memory store for each test (changing STORAGES resets them).
    settings.STORAGES = {**settings.STORAGES, "private": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db) -> User:
    return UserFactory()
