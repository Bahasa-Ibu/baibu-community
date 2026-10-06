from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from baibu.core.tasks import HEARTBEAT_CACHE_KEY
from baibu.core.tasks import heartbeat

pytestmark = pytest.mark.django_db


def test_health_ok_without_worker_heartbeat(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "cache": "ok", "worker": "unknown"}


def test_heartbeat_task_marks_worker_ok(client):
    heartbeat.delay()
    assert client.get(reverse("health")).json()["worker"] == "ok"


def test_old_heartbeat_reports_stale_worker(client, settings):
    settings.WORKER_HEARTBEAT_STALE_SECONDS = 60
    cache.set(HEARTBEAT_CACHE_KEY, (timezone.now() - timedelta(minutes=5)).isoformat())
    assert client.get(reverse("health")).json()["worker"] == "stale"


def test_unreadable_heartbeat_reports_unknown(client):
    cache.set(HEARTBEAT_CACHE_KEY, "not-a-date")
    assert client.get(reverse("health")).json()["worker"] == "unknown"


def test_database_failure_returns_503(client):
    with mock.patch("baibu.core.views.connection") as connection:
        connection.cursor.side_effect = RuntimeError("database down")
        response = client.get(reverse("health"))
    assert response.status_code == 503
    assert response.json()["database"] == "error"


def test_cache_failure_returns_503(client):
    with mock.patch("baibu.core.views.cache") as broken_cache:
        broken_cache.set.side_effect = RuntimeError("cache down")
        broken_cache.get.return_value = None
        response = client.get(reverse("health"))
    assert response.status_code == 503
    assert response.json()["cache"] == "error"
