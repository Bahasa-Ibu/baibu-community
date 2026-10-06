from datetime import date

import pytest
from django.urls import reverse

from baibu.metrics.models import DailyMetric
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_admin_lists_rollups_read_only(client):
    metric = DailyMetric.objects.create(date=date(2026, 3, 11), name="consent", dimension="chat:none", value=3)
    assert str(metric) == "2026-03-11 consent [chat:none]: 3"
    assert str(DailyMetric(date=date(2026, 3, 11), name="users_new", value=1)) == "2026-03-11 users_new: 1"
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert client.get(reverse("admin:metrics_dailymetric_changelist")).status_code == 200
    assert client.get(reverse("admin:metrics_dailymetric_change", args=[metric.pk])).status_code == 200
    assert client.get(reverse("admin:metrics_dailymetric_add")).status_code == 403
    assert (
        client.post(reverse("admin:metrics_dailymetric_delete", args=[metric.pk]), {"post": "yes"}).status_code == 403
    )
    assert DailyMetric.objects.filter(pk=metric.pk).exists()
