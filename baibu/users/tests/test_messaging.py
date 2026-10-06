import logging

import pytest
from django.core.checks import run_checks

from baibu.users import messaging
from baibu.users.phone import mask_phone
from baibu.users.phone import normalize_phone


@pytest.fixture(autouse=True)
def _empty_outbox():
    messaging.MemoryMessagingProvider.outbox.clear()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("+1 201-555-0123", "+12015550123"),
        ("(+44) 7700 900.123", "+447700900123"),
        ("0044 7700 900123", "+447700900123"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_phone(typed, expected):
    assert normalize_phone(typed) == expected


def test_mask_phone_keeps_last_two_digits():
    assert mask_phone("+12015550123") == "...23"
    assert mask_phone("1") == "..."


def test_memory_provider_records_messages(settings):
    settings.MESSAGING_PROVIDER = "baibu.users.messaging.MemoryMessagingProvider"
    messaging.send_text("+12015550123", "Hello")
    assert messaging.MemoryMessagingProvider.outbox == [messaging.SentText(phone="+12015550123", text="Hello")]


def test_console_provider_logs_message(settings, caplog):
    settings.MESSAGING_PROVIDER = "baibu.users.messaging.ConsoleMessagingProvider"
    with caplog.at_level(logging.INFO, logger="baibu.users.messaging"):
        messaging.send_text("+12015550123", "Your code is 123456")
    assert "Your code is 123456" in caplog.text
    assert "provider=console phone=...23" in caplog.text


class FailingProvider(messaging.MessagingProvider):
    name = "failing"

    def send_text(self, phone, text):
        raise messaging.MessagingError


def test_provider_failure_is_logged_without_the_number(settings, caplog):
    settings.MESSAGING_PROVIDER = f"{__name__}.FailingProvider"
    with caplog.at_level(logging.WARNING), pytest.raises(messaging.MessagingError):
        messaging.send_text("+12015550123", "Hello")
    assert "provider=failing phone=...23" in caplog.text
    assert "+12015550123" not in caplog.text


def test_base_provider_must_be_subclassed():
    with pytest.raises(NotImplementedError):
        messaging.MessagingProvider().send_text("+12015550123", "Hello")


def _check_ids():
    return [message.id for message in run_checks(include_deployment_checks=True, tags=["security"])]


def test_deploy_check_warns_about_console_provider(settings):
    settings.PHONE_SIGN_IN_ENABLED = True
    settings.MESSAGING_PROVIDER = "baibu.users.messaging.ConsoleMessagingProvider"
    assert "users.W001" in _check_ids()
    settings.MESSAGING_PROVIDER = f"{__name__}.FailingProvider"
    assert "users.W001" not in _check_ids()
    settings.PHONE_SIGN_IN_ENABLED = False
    settings.MESSAGING_PROVIDER = "baibu.users.messaging.ConsoleMessagingProvider"
    assert "users.W001" not in _check_ids()
