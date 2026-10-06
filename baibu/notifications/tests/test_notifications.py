from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils import translation

from baibu.notifications import kinds
from baibu.notifications import services
from baibu.notifications.models import Notification
from baibu.notifications.tasks import delete_old_notifications
from baibu.submissions.models import Submission
from baibu.submissions.services import review
from baibu.submissions.tests.factories import SubmissionFactory
from baibu.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

INBOX = reverse("notifications:inbox")


def test_notify_creates_and_counts(user):
    note = services.notify(user, kind="custom", title="Hello", body="Some news", link="/contribute/")
    assert note.display_title == "Hello"
    assert note.display_body == "Some news"
    assert str(note) == "Hello"
    assert services.unread_count(user) == 1
    services.mark_read(note)
    services.mark_read(note)
    assert note.is_read
    assert services.unread_count(user) == 0


def test_notify_drops_external_links_and_skips_inactive_or_disabled(user, settings):
    assert services.notify(user, kind="custom", title="x", link="https://evil.example.com/").link == ""
    user.is_active = False
    assert services.notify(user, kind="custom", title="x") is None
    user.is_active = True
    settings.NOTIFICATIONS_ENABLED = False
    assert services.notify(user, kind="custom", title="x") is None


def test_notify_never_breaks_the_caller(user):
    with mock.patch.object(Notification.objects, "create", side_effect=RuntimeError("db")):
        assert services.notify(user, kind="custom", title="x") is None


def test_registered_kinds_are_translated_when_shown(user):
    kinds.register("greeting", title="Hello %(name)s", body="Body for %(name)s")
    note = services.notify(user, kind="greeting", params={"name": "Ana"})
    assert note.display_title == "Hello Ana"
    assert note.display_body == "Body for Ana"
    broken = services.notify(user, kind="greeting", params={"other": 1})
    assert broken.display_title == "Hello %(name)s"
    accepted = services.notify(user, kind="submission_accepted")
    with translation.override("fr"):
        # No catalogue for French here: the source text shows, proving it is resolved at display time.
        assert accepted.display_title == "Your contribution was accepted"


def test_review_notifies_the_contributor(admin_user):
    submission = SubmissionFactory(status=Submission.Status.NEEDS_REVIEW)
    assert review(submission, Submission.Status.REJECTED, reviewer=admin_user) is True
    submission.refresh_from_db()
    assert submission.reviewed_by == admin_user
    assert submission.reviewed_at is not None
    note = submission.user.notifications.get()
    assert note.kind == "submission_rejected"
    assert note.display_title == "Your contribution was not accepted"
    assert note.link == reverse("submissions:list")
    # Not allowed from rejected: nothing changes, nobody is notified.
    assert review(submission, Submission.Status.VERIFIED) is False
    assert submission.user.notifications.count() == 1
    with pytest.raises(ValueError, match="Not a review decision"):
        review(submission, Submission.Status.PENDING)


def test_inbox_lists_own_notifications(client, user):
    services.notify(user, kind="submission_accepted", link="/contribute/")
    services.notify(UserFactory(), kind="custom", title="Someone else's")
    client.force_login(user)
    page = client.get(INBOX).content.decode()
    assert "Your contribution was accepted" in page
    assert "Someone else" not in page
    assert "Mark all as read" in page
    # The nav shows the unread count.
    assert "Notifications, 1 unread" in page


def test_inbox_empty_and_paginated(client, user):
    client.force_login(user)
    assert "no notifications" in client.get(INBOX).content.decode()
    for n in range(31):
        services.notify(user, kind="custom", title=f"Note {n}")
    page = client.get(INBOX).content.decode()
    assert "Older" in page
    assert "Newer" in client.get(f"{INBOX}?page=2").content.decode()


def test_open_marks_read_and_follows_internal_link(client, user):
    client.force_login(user)
    with_link = services.notify(user, kind="custom", title="a", link="/contribute/")
    without = services.notify(user, kind="custom", title="b")
    assert client.post(reverse("notifications:open", args=[with_link.pk])).url == "/contribute/"
    assert client.post(reverse("notifications:open", args=[without.pk])).url == INBOX
    assert services.unread_count(user) == 0
    other = services.notify(UserFactory(), kind="custom", title="c")
    assert client.post(reverse("notifications:open", args=[other.pk])).status_code == 404
    assert client.get(reverse("notifications:open", args=[with_link.pk])).status_code == 405


def test_mark_all_read(client, user):
    client.force_login(user)
    services.notify(user, kind="custom", title="a")
    services.notify(user, kind="custom", title="b")
    assert client.post(reverse("notifications:mark_all_read")).url == INBOX
    assert services.unread_count(user) == 0


def test_inbox_requires_sign_in(client):
    assert reverse("account_login") in client.get(INBOX).url


def test_old_read_notifications_are_deleted(user, settings):
    settings.NOTIFICATIONS_RETENTION_DAYS = 30
    old_read = services.notify(user, kind="custom", title="old read")
    old_unread = services.notify(user, kind="custom", title="old unread")
    recent_read = services.notify(user, kind="custom", title="recent read")
    services.mark_all_read(user)
    Notification.objects.filter(pk=old_unread.pk).update(read_at=None)
    Notification.objects.filter(pk__in=[old_read.pk, old_unread.pk]).update(
        created_at=timezone.now() - timedelta(days=31)
    )
    assert delete_old_notifications() == 1
    assert set(Notification.objects.values_list("pk", flat=True)) == {old_unread.pk, recent_read.pk}


def test_admin_is_read_only(client, admin_user, user):
    note = services.notify(user, kind="submission_accepted")
    client.force_login(admin_user)
    assert client.get(reverse("admin:notifications_notification_changelist")).status_code == 200
    url = reverse("admin:notifications_notification_change", args=[note.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {}).status_code == 403
    assert client.get(reverse("admin:notifications_notification_add")).status_code == 403
