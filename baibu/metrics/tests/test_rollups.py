from datetime import date
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError
from django.core.management import call_command
from django.utils import timezone

from baibu.chat.models import Message
from baibu.chat.models import Run
from baibu.chat.models import ToolInvocation
from baibu.metrics import rollups
from baibu.metrics.models import DailyMetric
from baibu.metrics.tasks import compute_daily_metrics
from baibu.submissions.models import Submission
from baibu.users.models import ConsentRecord
from baibu.users.tests.factories import ConsentRecordFactory

from . import helpers
from .helpers import at

pytestmark = pytest.mark.django_db

DAY = date(2026, 3, 11)  # a Wednesday
NEXT = DAY + timedelta(days=1)
BEFORE = DAY - timedelta(days=1)


@pytest.fixture(autouse=True)
def _platform_time_zone(settings):
    # Seven hours ahead of UTC, so local and UTC days differ.
    settings.TIME_ZONE = "Asia/Jakarta"
    settings.METRICS_RETENTION_WEEKS = 3


def stored(day=DAY) -> dict:
    return {(row.name, row.dimension): row.value for row in DailyMetric.objects.filter(date=day)}


def test_days_follow_the_platform_time_zone():
    person = helpers.user()
    helpers.message(person, at(DAY, 23, 30))  # 16:30 UTC on DAY
    helpers.message(person, at(NEXT, 0, 30))  # 17:30 UTC on DAY, but the next local day
    helpers.message(person, at(DAY, 0, 10))  # 17:10 UTC the day before, but this local day
    assert rollups.compute_day(DAY)["messages_user", ""] == 2
    assert rollups.compute_day(NEXT)["messages_user", ""] == 1
    assert rollups.day_start(DAY).utcoffset() == timedelta(hours=7)


def test_active_users_count_people_who_chatted_or_contributed():
    chatter, contributor, both, idle, replied_to = (helpers.user() for _ in range(5))
    helpers.message(chatter, at(DAY, 9))
    helpers.message(chatter, at(DAY, 10))
    helpers.submission(contributor, at(DAY, 11))
    helpers.message(both, at(DAY, 8))
    helpers.submission(both, at(DAY, 9))
    helpers.message(idle, at(BEFORE))
    # Only assistant messages that day: not active.
    helpers.message(replied_to, at(DAY), role=Message.Role.ASSISTANT)

    values = rollups.compute_day(DAY)
    assert values["active_users", ""] == 3
    assert values["chat_users", ""] == 2
    assert values["contributors", ""] == 2
    assert values["messages_user", ""] == 3
    assert values["messages_assistant", ""] == 1


def test_seven_and_thirty_day_windows_end_on_the_day():
    in_week, week_edge, out_of_week, month_edge, out_of_month = (helpers.user() for _ in range(5))
    helpers.message(in_week, at(DAY))
    helpers.message(week_edge, at(DAY - timedelta(days=6), 0, 5))
    helpers.submission(out_of_week, at(DAY - timedelta(days=7), 23, 55))
    helpers.message(month_edge, at(DAY - timedelta(days=29)))
    helpers.message(out_of_month, at(DAY - timedelta(days=30)))
    helpers.message(in_week, at(NEXT))  # after the day: ignored

    values = rollups.compute_day(DAY)
    assert values["active_users", ""] == 1
    assert values["active_users_7d", ""] == 2
    assert values["active_users_30d", ""] == 4


def test_new_and_total_users():
    helpers.user(joined=at(BEFORE))
    helpers.user(joined=at(DAY, 0, 1))
    helpers.user(joined=at(DAY, 23, 59))
    helpers.user(joined=at(NEXT, 0, 1))
    values = rollups.compute_day(DAY)
    assert values["users_new", ""] == 2
    assert values["users_total", ""] == 3


def test_conversations_by_language():
    person = helpers.user()
    helpers.conversation(person, at(DAY), language_code="en")
    helpers.conversation(person, at(DAY), language_code="en")
    helpers.conversation(person, at(DAY), language_code="fr")
    helpers.conversation(person, at(DAY), language_code="")
    helpers.conversation(person, at(BEFORE), language_code="fr")
    values = rollups.compute_day(DAY)
    assert values["conversations", ""] == 4
    assert values["conversations_by_language", "en"] == 2
    assert values["conversations_by_language", "fr"] == 1
    assert values["conversations_by_language", "unknown"] == 1


def test_runs_by_status_and_reply_times():
    person = helpers.user()
    convo = helpers.conversation(person, at(DAY))
    for seconds in (1, 2, 3, 4, 10):
        helpers.run(convo, at(DAY, 10), seconds=seconds)
    helpers.run(convo, at(DAY, 11), status=Run.Status.FAILED, seconds=60)
    helpers.run(convo, at(DAY, 11), status=Run.Status.QUEUED, seconds=None)
    helpers.run(convo, at(BEFORE), seconds=100)

    values = rollups.compute_day(DAY)
    assert values["runs", "completed"] == 5
    assert values["runs", "failed"] == 1
    assert values["runs", "queued"] == 1
    assert ("runs", "running") not in values
    # Completed runs only, from creation to completion.
    assert values["reply_time_median_ms", ""] == 3000
    assert values["reply_time_p90_ms", ""] == 7600


def test_no_reply_times_without_completed_runs():
    values = rollups.compute_day(DAY)
    assert ("reply_time_median_ms", "") not in values
    assert ("reply_time_p90_ms", "") not in values
    assert values["active_users", ""] == 0
    assert values["submissions", ""] == 0


def test_tool_calls_by_status():
    convo = helpers.conversation(helpers.user(), at(DAY))
    helpers.tool_call(convo, at(DAY))
    helpers.tool_call(convo, at(DAY))
    helpers.tool_call(convo, at(DAY), status=ToolInvocation.Status.FAILED)
    values = rollups.compute_day(DAY)
    assert values["tool_calls", "completed"] == 2
    assert values["tool_calls", "failed"] == 1


def test_submissions_by_status_and_language():
    person = helpers.user()
    helpers.submission(person, at(DAY), status=Submission.Status.VERIFIED, language_code="en")
    helpers.submission(person, at(DAY), status=Submission.Status.VERIFIED, language_code="sw")
    helpers.submission(person, at(DAY), status=Submission.Status.NEEDS_REVIEW, language_code="en")
    helpers.submission(person, at(BEFORE), status=Submission.Status.REJECTED)
    values = rollups.compute_day(DAY)
    assert values["submissions", ""] == 3
    assert values["submissions_by_status", "verified"] == 2
    assert values["submissions_by_status", "needs_review"] == 1
    assert ("submissions_by_status", "rejected") not in values
    assert values["submissions_by_language", "en"] == 2
    assert values["submissions_by_language", "sw"] == 1


def test_consent_is_each_users_latest_tier_at_the_end_of_the_day():
    changed_later, revoked, chat_only, newcomer = (helpers.user() for _ in range(4))
    ConsentRecordFactory(
        user=changed_later, tier=ConsentRecord.Tier.EVAL_ONLY, granted_at=at(BEFORE), revoked_at=at(NEXT)
    )
    ConsentRecordFactory(user=changed_later, tier=ConsentRecord.Tier.TRAINING_ELIGIBLE, granted_at=at(NEXT))
    # Latest record revoked before the end of the day: counts as none.
    ConsentRecordFactory(
        user=revoked, tier=ConsentRecord.Tier.TRAINING_ELIGIBLE, granted_at=at(BEFORE), revoked_at=at(DAY)
    )
    ConsentRecordFactory(user=chat_only, scope="chat", tier=ConsentRecord.Tier.NONE, granted_at=at(DAY, 23))
    ConsentRecordFactory(user=newcomer, tier=ConsentRecord.Tier.EVAL_ONLY, granted_at=at(NEXT, 0, 1))

    consent = {k: v for (name, k), v in rollups.compute_day(DAY).items() if name == "consent"}
    assert consent == {"platform:eval_only": 1, "platform:none": 1, "chat:none": 1}
    later = {k: v for (name, k), v in rollups.compute_day(NEXT).items() if name == "consent"}
    assert later == {"platform:training_eligible": 1, "platform:none": 1, "platform:eval_only": 1, "chat:none": 1}


def test_weekly_retention_cohorts():
    week = rollups.week_start(DAY)  # Monday 2026-03-09
    assert week == date(2026, 3, 9)
    two_weeks_ago = week - timedelta(weeks=2)
    cohort = [helpers.user(joined=at(two_weeks_ago + timedelta(days=offset))) for offset in (0, 3, 6)]
    helpers.user(joined=at(two_weeks_ago - timedelta(days=1)))  # the Sunday before: an earlier cohort
    joined_this_week = helpers.user(joined=at(week))
    # Active this week (two weeks after joining): two of the three, any day of the week.
    helpers.message(cohort[0], at(week))
    helpers.submission(cohort[1], at(week + timedelta(days=6), 23))
    helpers.message(cohort[2], at(week - timedelta(days=1)))  # last week, not this one
    helpers.message(joined_this_week, at(DAY))

    cells = rollups.compute_retention(DAY)
    assert cells[two_weeks_ago, "retention_cohort_size", ""] == 3
    assert cells[two_weeks_ago, "retention_active", "2"] == 2
    assert cells[week, "retention_cohort_size", ""] == 1
    # Week 0 is never stored as retention.
    assert (week, "retention_active", "0") not in cells
    # The cohort before has one user and nobody active this week.
    assert cells[week - timedelta(weeks=3), "retention_cohort_size", ""] == 1
    assert cells[week - timedelta(weeks=3), "retention_active", "3"] == 0
    # Empty cohorts are marked for removal.
    assert cells[week - timedelta(weeks=1), "retention_cohort_size", ""] is None
    assert cells[week - timedelta(weeks=1), "retention_active", "1"] is None


def test_storing_a_day_again_replaces_its_values():
    person = helpers.user(joined=at(rollups.week_start(DAY)))
    helpers.conversation(person, at(DAY), language_code="fr")
    helpers.message(person, at(DAY))
    rollups.store_day(DAY)
    first = stored()
    rollups.store_day(DAY)
    assert stored() == first
    assert DailyMetric.objects.filter(date=DAY, name="messages_user").count() == 1

    # Data changed since (a conversation deleted): the stored day follows it,
    # and breakdown values that no longer exist are removed.
    person.conversations.filter(language_code="fr").delete()
    rollups.store_day(DAY)
    again = stored()
    assert ("conversations_by_language", "fr") not in again
    assert again["conversations", ""] == 1
    assert again["messages_user", ""] == 1


def test_storing_writes_retention_and_removes_empty_cohorts():
    week = rollups.week_start(DAY)
    person = helpers.user(joined=at(week - timedelta(weeks=1)))
    helpers.message(person, at(DAY))
    rollups.store_day(DAY)
    cohort = {(r.name, r.dimension): r.value for r in DailyMetric.objects.filter(date=week - timedelta(weeks=1))}
    assert cohort == {("retention_cohort_size", ""): 1, ("retention_active", "1"): 1}

    person.delete()
    rollups.store_day(DAY)
    assert not DailyMetric.objects.filter(date=week - timedelta(weeks=1)).exists()


def test_store_range_and_catch_up():
    assert rollups.store_range(DAY, BEFORE) == 0
    today = DAY + timedelta(days=10)
    assert rollups.days_to_catch_up(today) == (today - timedelta(days=1),) * 2

    rollups.store_range(DAY, DAY + timedelta(days=2))
    assert DailyMetric.objects.filter(name="active_users").count() == 3
    assert rollups.days_to_catch_up(today) == (DAY + timedelta(days=3), today - timedelta(days=1))
    assert rollups.days_to_catch_up(DAY + timedelta(days=3)) == (DAY + timedelta(days=2),) * 2

    # A long gap is filled back to METRICS_CATCH_UP_DAYS only.
    far = DAY + timedelta(days=100)
    assert rollups.days_to_catch_up(far) == (far - timedelta(days=7), far - timedelta(days=1))


def test_nightly_task_computes_yesterday():
    person = helpers.user()
    yesterday = timezone.localdate() - timedelta(days=1)
    helpers.message(person, at(yesterday))
    result = compute_daily_metrics.delay().get()
    assert result == {"first": yesterday.isoformat(), "last": yesterday.isoformat(), "days": 1}
    assert stored(yesterday)["active_users", ""] == 1


def test_nightly_task_is_scheduled(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["metrics-daily"]
    assert entry["task"] == "baibu.metrics.tasks.compute_daily_metrics"
    assert entry["schedule"].hour == {settings.METRICS_COMPUTE_HOUR}


def test_backfill_command():
    person = helpers.user()
    helpers.message(person, at(DAY))
    out = StringIO()
    call_command("compute_metrics", "--start", "2026-03-09", "--end", "2026-03-12", stdout=out)
    assert "Computed 4 day(s), 2026-03-09 to 2026-03-12." in out.getvalue()
    assert DailyMetric.objects.filter(name="active_users").count() == 4
    assert stored()["active_users", ""] == 1

    call_command("compute_metrics", "--end", "2026-03-11", stdout=StringIO())
    assert DailyMetric.objects.filter(name="active_users").count() == 4


def test_backfill_command_defaults_to_yesterday():
    call_command("compute_metrics", stdout=StringIO())
    assert DailyMetric.objects.get(name="active_users").date == timezone.localdate() - timedelta(days=1)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--start", "2026-03-12", "--end", "2026-03-11"], "--start must not be after --end"),
        (["--start", "11/03/2026"], "Not a date"),
        (["--end", "2999-01-01"], "Only finished days"),
    ],
)
def test_backfill_command_refuses_bad_ranges(args, message):
    with pytest.raises(CommandError, match=message):
        call_command("compute_metrics", *args, stdout=StringIO())
