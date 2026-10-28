"""Sorting provider failures, and retrying the ones that pass by themselves.

Language and speech providers fail in different ways: a quota that clears
after a few seconds, a brief outage, a timeout, a refused key, a request
that will never work. Only the first two are worth waiting out inside one
call; the rest are reported as they are.
"""

import logging
import random
import re
import time
from collections.abc import Callable

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT = "timeout"
RATE_LIMITED = "rate_limited"
TRANSIENT = "transient_provider_error"
PERMISSION_DENIED = "permission_denied"
BAD_REQUEST = "bad_request"
OTHER = "other"

# Failures that usually clear if the same call is made again shortly.
RETRYABLE = frozenset({RATE_LIMITED, TRANSIENT})

_STATUS = re.compile(r"\b(?:http(?:/\d(?:\.\d)?)?|status(?:_code| code)?|code|error)[\s\"':=]*(4\d\d|5\d\d)\b", re.I)
_RATE_WORDS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "resource_exhausted",
    "resource exhausted",
)


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 400 <= value <= 599:
            return value
    match = _STATUS.search(str(exc))
    return int(match.group(1)) if match else None


def classify(exc: BaseException) -> str:
    """The kind of failure ``exc`` is, as one of the constants above."""
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    status = _status_of(exc)
    if status == 429 or "ratelimit" in name or any(word in message for word in _RATE_WORDS):
        return RATE_LIMITED
    if "timeout" in name or "timed out" in message:
        return TIMEOUT
    if status in (500, 502, 503, 504) or "serviceunavailable" in name or "internalservererror" in name:
        return TRANSIENT
    if status in (401, 403) or "authentication" in name or "permissiondenied" in name:
        return PERMISSION_DENIED
    if status in (400, 404, 413, 422) or "badrequest" in name:
        return BAD_REQUEST
    return OTHER


def call_with_retry[T](call: Callable[[], T]) -> T:
    """Run ``call``, retrying rate limits and brief outages with growing waits.

    Gives up once ``CHAT_PROVIDER_RETRY_SECONDS`` of waiting is used (0 turns
    retrying off) and re-raises the last error. Other failures are raised at
    once, so a request that cannot work does not wait.
    """
    budget = settings.CHAT_PROVIDER_RETRY_SECONDS
    waited = 0.0
    delay = 1.0
    while True:
        try:
            return call()
        except Exception as exc:
            if classify(exc) not in RETRYABLE or waited >= budget:
                raise
            pause = min(delay * random.uniform(0.75, 1.25), budget - waited)  # noqa: S311
            logger.warning("Provider call failed (%s); retrying in %.1fs", classify(exc), pause)
            time.sleep(pause)
            waited += pause
            delay = min(delay * 2, 16.0)
