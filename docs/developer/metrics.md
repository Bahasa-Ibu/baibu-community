# Usage metrics

Staff can see how the platform is used at `/staff/usage/`: how many people
are active, how many conversations and submissions there are, how replies
perform, and weekly retention. The page reads **rollups**: aggregate
integers per day, computed in the background. It never shows message text,
names, email addresses or a row per person, and the rollups themselves hold
none.

## Who can see it

Signed-in staff (`is_staff`) who also have the permission
*Usage metrics | daily metric | Can view daily metric*
(`metrics.view_dailymetric`). Superusers have every permission. Give it to
other staff in the admin, on the user or on a group. Staff with it see a
*Usage* link in the header. Anyone else who opens the page is sent to
sign in (if signed out) or refused with 403.

## How the rollups are computed

- **Days** are calendar days in the platform time zone (`DJANGO_TIME_ZONE`),
  from midnight to midnight. An event belongs to the day its timestamp
  falls on in that zone.
- **Nightly.** Celery beat runs `baibu.metrics.tasks.compute_daily_metrics`
  at `METRICS_COMPUTE_HOUR`:`METRICS_COMPUTE_MINUTE` (default 02:15,
  platform time). It computes yesterday, and also every day since the last
  computed day if the worker missed nights, up to `METRICS_CATCH_UP_DAYS`
  days back.
- **Backfill.** For a new installation, or to recompute a range:

    ```sh
    docker compose run --rm django python manage.py compute_metrics --start 2026-01-01 --end 2026-03-31
    ```

    `--end` defaults to yesterday and `--start` to `--end`. Only finished days
    (before today) can be computed.
- **Idempotent.** Computing a day again replaces everything stored for it
  (including breakdown values that no longer occur), so the task and the
  command can run any number of times.
- **From current data.** Rollups are computed from the tables as they are at
  the time: deleted conversations, submissions and accounts no longer count.
  Values already stored keep their counts until that day is computed again,
  so a backfill over old days can lower them. Statuses (of a submission or a
  reply attempt) are the status at computation time.
- Staff accounts are counted like everyone else.

## Definitions

"Active" means: **the user sent at least one chat message (a message with
role `user`) or created at least one submission** in the period. Opening a
page, signing in, receiving an assistant reply or changing consent does not
make someone active.

Each row of `DailyMetric` has a `date`, a `name`, a `dimension` (blank for a
plain total, otherwise the value the breakdown is split by) and an integer
`value`. Breakdowns store only non-zero values; plain totals are stored even
when zero. For day *D*:

| Name | Dimension | Value |
| --- | --- | --- |
| `users_new` | | Users whose `date_joined` is on *D*. |
| `users_total` | | Users whose `date_joined` is before the end of *D*. |
| `active_users` | | Distinct active users on *D* (daily active users). |
| `active_users_7d` | | Distinct users active on at least one day from *D*−6 to *D* (weekly active users). |
| `active_users_30d` | | Distinct users active on at least one day from *D*−29 to *D* (monthly active users). |
| `chat_users` | | Distinct users who sent at least one chat message on *D*. |
| `contributors` | | Distinct users who created at least one submission on *D*. |
| `conversations` | | Conversations created on *D*. |
| `conversations_by_language` | language code, or `unknown` | The same, by the conversation's language. |
| `messages_user` | | Chat messages with role `user` created on *D*. |
| `messages_assistant` | | Chat messages with role `assistant` created on *D*. |
| `runs` | `queued`, `running`, `completed`, `failed` | Reply attempts (runs, including retries) created on *D*, by their current status. The page's *Failed reply attempts* is `runs` / `failed`. |
| `reply_time_median_ms` | | Median time from a run's creation to its completion, in milliseconds, over runs created on *D* that completed (interpolated, PostgreSQL `percentile_cont(0.5)`). Includes waiting in the queue and any tool calls. Not stored for a day without completed runs. |
| `reply_time_p90_ms` | | The 90th percentile of the same (`percentile_cont(0.9)`). |
| `tool_calls` | `completed`, `failed` | Tool invocations created on *D*, by status. |
| `submissions` | | Submissions created on *D*. |
| `submissions_by_status` | submission status | The same, by current status. |
| `submissions_by_language` | language code | The same, by language. |
| `consent` | `scope:tier`, e.g. `chat:eval_only` | Users per consent scope and tier at the end of *D*: for each user and scope, the latest record granted before the end of *D*; if that record was revoked before the end of *D*, the tier counts as `none`. Users who never chose in a scope are not counted for it. |

**Weekly retention.** A cohort is the users who joined (`date_joined`) in
one week, Monday to Sunday in the platform time zone. Rows are dated by the
cohort's Monday:

| Name | Dimension | Value |
| --- | --- | --- |
| `retention_cohort_size` | | Users in the cohort. |
| `retention_active` | *k*, from `1` to `METRICS_RETENTION_WEEKS` | Users in the cohort who were active at least once in the *k*-th week after their joining week (Monday to Sunday). |

Computing day *D* recomputes the cells that activity in *D*'s week can
change: for the week containing *D*, each of the `METRICS_RETENTION_WEEKS`
cohorts before it, plus the size of the cohort joining that week. A cell for
the current week is therefore partial until its Sunday has been computed.
Cohorts with no users are not stored.

## The usage page

- **At a glance**: the latest computed day, the last 7 days and the last
  30 days up to it. Counts of events (new users, conversations, messages,
  replies, failed attempts, tool calls, submissions) are sums of the daily
  values. Active users are the stored distinct counts (`active_users`,
  `active_users_7d`, `active_users_30d`), never sums, because one person
  active on two days is one active user.
- **Range.** *From* and *To* choose the days (inclusive) for the chart, the
  per-day table, the breakdowns and the retention cohorts (those whose
  Monday falls in the range). The default is the 30 days up to yesterday;
  at most `METRICS_MAX_RANGE_DAYS` days, and not in the future.
- **Chart**: an inline SVG bar chart of one per-day figure (no JavaScript or
  external files). Hover a bar for its value; the table below has every
  value.
- **Breakdowns** sum each breakdown over the range. *Current consent* is the
  snapshot at the last computed day in the range.
- **Download CSV**: every stored row dated in the range, as
  `date,name,dimension,value`, including retention rows whose cohort week
  starts in the range.

## Small counts

A breakdown by language or by consent tier, on a single day, could point at
one person (for example the only person who chats in a rare language). On
the page and in the CSV, these breakdowns (`conversations_by_language`,
`submissions_by_language`, `consent`) show values from 1 up to
`METRICS_MIN_GROUP_SIZE` − 1 as `<N` (default `<5`). The stored values are
exact. Totals, statuses and retention are not suppressed. Suppression is a
precaution for exports that get shared, not a guarantee: a suppressed value
can sometimes be worked out from the total. Set `METRICS_MIN_GROUP_SIZE=0`
to turn it off.

## Adding a metric

1. Add it to `METRICS` in `baibu/metrics/definitions.py` (label, how it adds
   up over days, whether it is a sensitive breakdown).
2. Compute it in `compute_day` in `baibu/metrics/rollups.py`. Return only
   counts.
3. To show it as a per-day column, add a `Column` to `COLUMNS` in
   `baibu/metrics/report.py`.
4. Document its exact definition in the table above, add tests, and run
   `compute_metrics` over past days if you want history for it.
