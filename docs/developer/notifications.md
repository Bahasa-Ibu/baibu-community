# Notifications

Users have an inbox at `/notifications/`; the navigation shows the number
of unread notifications. The platform currently notifies contributors when
a reviewer accepts or rejects their submission.

## Sending a notification

```python
from baibu.notifications.services import notify

notify(user, kind="submission_accepted", link="/contribute/")
```

- `kind` names what the notification is about. Kinds registered in
  `baibu/notifications/kinds.py` have translatable texts, rendered **when
  the notification is shown**, so each reader sees them in their own
  language. Parameters go in `params` and fill `%(name)s` placeholders.
- A notification of an unregistered kind shows the `title` and `body`
  passed to `notify()` as they are.
- `link` must be a path inside the platform (starting with `/`); anything
  else is dropped. Opening a notification marks it as read and follows the
  link.
- `notify()` never raises: a failure is logged and the caller's work
  carries on.

To add a kind in a feature app:

```python
from django.utils.translation import gettext_lazy as _
from baibu.notifications import kinds

kinds.register("event_reminder", title=_("Reminder: %(event)s"), body=_("It starts at %(time)s."))
```

## Retention

Read notifications older than `NOTIFICATIONS_RETENTION_DAYS` are deleted by
a daily Celery beat task. Unread notifications are kept. Deleting a user
deletes their notifications.
