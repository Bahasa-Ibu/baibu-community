"""Build synthetic activity at chosen times. ``created_at`` fields are set after
creation because the models fill them in automatically."""

from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta

from django.utils import timezone

from baibu.chat.models import Message
from baibu.chat.models import Run
from baibu.chat.models import ToolInvocation
from baibu.chat.tests.factories import ConversationFactory
from baibu.chat.tests.factories import MessageFactory
from baibu.submissions.tests.factories import SubmissionFactory
from baibu.users.tests.factories import UserFactory


def at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    """A moment on ``day`` in the platform time zone."""
    return datetime.combine(day, time(hour, minute), tzinfo=timezone.get_default_timezone())


def _stamp(obj, when: datetime, field: str = "created_at"):
    type(obj).objects.filter(pk=obj.pk).update(**{field: when})
    setattr(obj, field, when)
    return obj


def user(joined: datetime | None = None, **kwargs):
    return UserFactory(date_joined=joined or at(date(2020, 1, 1)), **kwargs)


def conversation(owner, when: datetime, language_code: str = "en"):
    return _stamp(ConversationFactory(user=owner, language_code=language_code), when)


def message(owner, when: datetime, role: str = Message.Role.USER, convo=None):
    convo = convo or conversation(owner, when)
    return _stamp(MessageFactory(conversation=convo, role=role), when)


def run(convo, when: datetime, status: str = Run.Status.COMPLETED, seconds: float | None = 2.0):
    trigger = message(convo.user, when, convo=convo)
    created = Run.objects.create(
        conversation=convo,
        triggering_message=trigger,
        status=status,
        idempotency_key=f"run-{trigger.pk}",
    )
    _stamp(created, when)
    if seconds is not None:
        _stamp(created, when + timedelta(seconds=seconds), "completed_at")
    return created


def tool_call(convo, when: datetime, status: str = ToolInvocation.Status.COMPLETED):
    parent = run(convo, when)
    call = ToolInvocation.objects.create(
        run=parent, tool_name="internet_search", call_id=f"call-{parent.pk}", status=status
    )
    return _stamp(call, when)


def submission(owner, when: datetime, **kwargs):
    return _stamp(SubmissionFactory(user=owner, **kwargs), when)
