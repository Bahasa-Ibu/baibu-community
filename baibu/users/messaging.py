"""Messaging providers: the pluggable way text messages reach a phone.

Phone sign-in sends one-time codes through the provider named by
``MESSAGING_PROVIDER`` (a dotted path to a :class:`MessagingProvider`
subclass). Two ship with the platform:

- ``ConsoleMessagingProvider`` (default): writes the message to the log.
  For development; nothing leaves the machine.
- ``MemoryMessagingProvider``: keeps messages in a list, for tests.

A deployment that sends real messages (SMS or a chat app) writes its own
subclass and implements :meth:`MessagingProvider.send_text`. See the
"Phone sign-in" page of the developer docs.
"""

import logging
from dataclasses import dataclass
from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string

from .phone import mask_phone

logger = logging.getLogger(__name__)


class MessagingError(Exception):
    """The provider could not send the message."""


class MessagingProvider:
    name = "provider"

    def send_text(self, phone: str, text: str) -> None:
        """Send ``text`` to ``phone`` (E.164, e.g. ``+15550100``).

        Raise :class:`MessagingError` if the message could not be sent.
        """
        raise NotImplementedError


class ConsoleMessagingProvider(MessagingProvider):
    """Logs each message instead of sending it. For development only."""

    name = "console"

    def send_text(self, phone: str, text: str) -> None:
        logger.info("Text message to %s:\n%s", phone, text)


@dataclass(frozen=True)
class SentText:
    phone: str
    text: str


class MemoryMessagingProvider(MessagingProvider):
    """Records messages in :attr:`outbox`, like Django's in-memory email backend."""

    name = "memory"
    outbox: list[SentText] = []

    def send_text(self, phone: str, text: str) -> None:
        self.outbox.append(SentText(phone=phone, text=text))


@cache
def _provider_class(path: str) -> type[MessagingProvider]:
    return import_string(path)


def get_provider() -> MessagingProvider:
    return _provider_class(settings.MESSAGING_PROVIDER)()


def send_text(phone: str, text: str) -> None:
    """Send a text through the configured provider; raises :class:`MessagingError`."""
    provider = get_provider()
    try:
        provider.send_text(phone, text)
    except MessagingError:
        logger.warning("Text message not sent; provider=%s phone=%s", provider.name, mask_phone(phone))
        raise
    logger.info("Text message sent; provider=%s phone=%s", provider.name, mask_phone(phone))
