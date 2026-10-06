"""Settings for the test suite: fast hashing, in-memory email and cache."""

from .base import *  # noqa: F403
from .base import TEMPLATES
from .base import env

SECRET_KEY = env("DJANGO_SECRET_KEY", default="test-only-not-secret")
ALLOWED_HOSTS = ["testserver", "localhost"]
TEST_RUNNER = "django.test.runner.DiscoverRunner"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": ""}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "private": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore[index]
MESSAGING_PROVIDER = "baibu.users.messaging.MemoryMessagingProvider"

# Tests of the translation workflow turn this on; other tests should not
# query for publications on every request.
LOCALIZATION_SYNC = False
