import csv
import io
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from baibu.metrics import rollups
from baibu.metrics.models import DailyMetric
from baibu.users.tests.factories import UserFactory

from . import helpers
from .helpers import at

pytestmark = pytest.mark.django_db

USAGE_URL = reverse("metrics:usage")
EXPORT_URL = reverse("metrics:export")


def yesterday():
    return timezone.localdate() - timedelta(days=1)


@pytest.fixture
def staff(client):
    member = UserFactory(is_staff=True)
    member.user_permissions.add(Permission.objects.get(codename="view_dailymetric"))
    client.force_login(member)
    return member


@pytest.fixture
def activity():
    """Synthetic activity yesterday, stored as rollups."""
    day = yesterday()
    people = [helpers.user(joined=at(day)) for _ in range(6)]
    for person in people:
        helpers.message(person, at(day, 10))
    helpers.conversation(people[0], at(day), language_code="sw")
    helpers.submission(people[0], at(day))
    rollups.store_day(day)
    return people


def test_anonymous_users_are_sent_to_sign_in(client):
    for url in (USAGE_URL, EXPORT_URL):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("account_login") in response.url


def test_non_staff_are_refused(client, user):
    user.user_permissions.add(Permission.objects.get(codename="view_dailymetric"))
    client.force_login(user)
    assert client.get(USAGE_URL).status_code == 403
    assert client.get(EXPORT_URL).status_code == 403


def test_staff_need_the_view_permission(client):
    client.force_login(UserFactory(is_staff=True))
    assert client.get(USAGE_URL).status_code == 403
    assert reverse("metrics:usage") not in client.get(reverse("home")).content.decode()


def test_superusers_and_permitted_staff_see_the_page(client, staff):
    response = client.get(USAGE_URL)
    assert response.status_code == 200
    assert f'href="{USAGE_URL}"' in client.get(reverse("home")).content.decode()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    assert client.get(USAGE_URL).status_code == 200


def test_only_get_is_allowed(client, staff):
    assert client.post(USAGE_URL).status_code == 405


def test_empty_state(client, staff):
    content = client.get(USAGE_URL).content.decode()
    # The form shows the default range and chart.
    assert f'name="end" value="{yesterday().isoformat()}"' in content
    assert '<option value="active_users" selected>' in content
    assert 'id="usage-empty"' in content
    assert "compute_metrics --start" in content
    assert "No figures for these days." in content
    assert "No cohorts start in these days." in content


def test_page_shows_counts_and_no_personal_details(client, staff, activity):
    response = client.get(USAGE_URL)
    content = response.content.decode()
    assert 'id="usage-empty"' not in content
    headlines = {str(h.label): h.values for h in response.context["headlines"]}
    assert headlines["Active users"] == [6, 6, 6]
    assert headlines["Messages sent"] == [6, 6, 6]
    assert headlines["Conversations started"] == [7, 7, 7]
    assert headlines["Submissions"] == [1, 1, 1]
    assert response.context["users_total"] == 6  # the staff member joined today
    first_row = response.context["rows"][0]
    assert first_row["date"] == yesterday()
    assert first_row["computed"]
    assert len(response.context["rows"]) == 30
    assert not response.context["rows"][1]["computed"]
    assert "Not computed" in content
    # Small breakdowns by language are not shown exactly.
    languages = {b["metric"].name: dict(b["rows"]) for b in response.context["breakdowns"]}
    assert languages["conversations_by_language"] == {"en": 6, "sw": "<5"}
    assert languages["submissions_by_language"] == {"en": "<5"}
    # Never text, names or addresses.
    for person in activity:
        assert person.email not in content
        assert person.name not in content
        for message in person.conversations.first().messages.all():
            assert message.content not in content


def test_chart_draws_one_bar_per_day(client, staff, activity):
    response = client.get(USAGE_URL, {"chart": "messages_user"})
    chart = response.context["chart"]
    assert chart["column"].key == "messages_user"
    assert len(chart["bars"]) == 30
    assert chart["bars"][-1]["value"] == 6
    assert chart["bars"][-1]["height"] == chart["height"]
    assert chart["bars"][0]["height"] == 0
    content = response.content.decode()
    assert "<svg" in content
    assert "<script" not in content.split("<svg", 1)[1].split("</svg>", 1)[0]


def test_suppression_can_be_turned_off(client, staff, activity, settings):
    settings.METRICS_MIN_GROUP_SIZE = 0
    response = client.get(USAGE_URL)
    languages = {b["metric"].name: dict(b["rows"]) for b in response.context["breakdowns"]}
    assert languages["conversations_by_language"] == {"en": 6, "sw": 1}
    assert "are shown as" not in response.content.decode()


def test_range_parameters(client, staff, activity):
    day = yesterday()
    response = client.get(USAGE_URL, {"start": (day - timedelta(days=6)).isoformat(), "end": day.isoformat()})
    assert len(response.context["rows"]) == 7
    response = client.get(USAGE_URL, {"end": (day - timedelta(days=1)).isoformat()})
    assert len(response.context["rows"]) == 30
    assert not response.context["has_data"]


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-02-10", "end": "2026-02-01"},
        {"start": "2020-01-01", "end": "2026-01-01"},
        {"end": "2999-01-01"},
        {"start": "not-a-date"},
        {"chart": "secret"},
    ],
)
def test_invalid_ranges_show_an_error_and_the_default(client, staff, params):
    response = client.get(USAGE_URL, params)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert response.context["end"] == yesterday()
    assert len(response.context["rows"]) == 30
    assert client.get(EXPORT_URL, params).status_code == 400


def test_retention_table(client, staff, settings):
    settings.METRICS_RETENTION_WEEKS = 2
    week = rollups.week_start(yesterday())
    cohort_week = week - timedelta(weeks=1)
    people = [helpers.user(joined=at(cohort_week)) for _ in range(4)]
    helpers.message(people[0], at(week))
    rollups.store_day(week)
    response = client.get(USAGE_URL, {"start": (cohort_week - timedelta(days=1)).isoformat()})
    retention = response.context["retention"]
    assert retention["weeks"] == [1, 2]
    cohort = next(c for c in retention["cohorts"] if c["week"] == cohort_week)
    assert cohort["size"] == 4
    assert cohort["cells"] == [{"value": 1, "percent": 25}, None]
    assert "(25%)" in response.content.decode()
    # A cell without its cohort size (not written by the rollups) is ignored.
    DailyMetric.objects.create(date=cohort_week - timedelta(weeks=1), name="retention_active", dimension="1", value=2)
    response = client.get(USAGE_URL, {"start": (cohort_week - timedelta(days=8)).isoformat()})
    assert cohort_week - timedelta(weeks=1) not in [c["week"] for c in response.context["retention"]["cohorts"]]


def test_consent_snapshot(client, staff, activity):
    from baibu.users.models import ConsentRecord
    from baibu.users.tests.factories import ConsentRecordFactory

    for person in activity:
        ConsentRecordFactory(user=person, tier=ConsentRecord.Tier.EVAL_ONLY, granted_at=at(yesterday(), 1))
    rollups.store_day(yesterday())
    response = client.get(USAGE_URL)
    assert response.context["consent"] == [("platform", "eval_only", 6)]
    assert "platform: eval_only" in response.content.decode()


def test_csv_export(client, staff, activity):
    day = yesterday()
    response = client.get(EXPORT_URL, {"start": day.isoformat(), "end": day.isoformat()})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert f'filename="usage-{day}-{day}.csv"' in response["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows[0] == ["date", "name", "dimension", "value"]
    values = {(name, dimension): value for _date, name, dimension, value in rows[1:]}
    assert values["active_users", ""] == "6"
    assert values["conversations_by_language", "en"] == "6"
    assert values["conversations_by_language", "sw"] == "<5"
    # A one-day range holds only rows dated that day.
    assert len(rows) - 1 == DailyMetric.objects.filter(date=day).count()


def test_csv_export_defaults_to_thirty_days(client, staff):
    response = client.get(EXPORT_URL)
    day = yesterday()
    assert f"usage-{day - timedelta(days=29)}-{day}.csv" in response["Content-Disposition"]
    assert response.content.decode().strip() == "date,name,dimension,value"
