"""Notification texts, translated when shown.

A notification stores its kind and parameters, not finished text, so it is
displayed in the reader's language. Feature apps register their kinds here;
a notification of an unknown kind shows its stored ``title`` and ``body``.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Kind:
    title: str
    body: str = ""


KINDS: dict[str, Kind] = {
    "submission_accepted": Kind(
        title=_("Your contribution was accepted"),
        body=_("Thank you. A reviewer checked your writing and accepted it."),
    ),
    "submission_rejected": Kind(
        title=_("Your contribution was not accepted"),
        body=_("A reviewer checked your writing and could not accept it this time."),
    ),
    "chat_report_reviewed": Kind(
        title=_("Your report was reviewed"),
        body=_("Thank you for reporting a reply. Someone on our team has looked at it."),
    ),
}


def register(name: str, *, title, body="") -> None:
    KINDS[name] = Kind(title=title, body=body)
