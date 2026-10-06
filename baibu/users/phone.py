"""Phone numbers in international (E.164) format.

People type numbers with spaces, dashes, dots or brackets, and sometimes
``00`` instead of ``+``. :func:`normalize_phone` strips that formatting;
:data:`validate_e164` then checks the result is ``+`` followed by the country
code and number, at most 15 digits. Numbers in national format (without a
country code) are refused rather than guessed.
"""

import re

from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

# Characters people commonly use to group digits.
_FORMATTING = re.compile(r"[\s\-.()/]")

validate_e164 = RegexValidator(
    regex=r"^\+[1-9]\d{6,14}$",
    message=_("Enter a phone number in international format, starting with + and the country code."),
    code="invalid_phone",
)


def normalize_phone(value: str | None) -> str:
    """Return ``value`` without formatting characters; ``00`` becomes ``+``.

    The result is not validated; run :data:`validate_e164` on it.
    """
    phone = _FORMATTING.sub("", value or "")
    if phone.startswith("00"):
        phone = f"+{phone[2:]}"
    return phone


def mask_phone(phone: str) -> str:
    """Hide all but the last two digits, for logs."""
    return f"...{phone[-2:]}" if len(phone) > 2 else "..."
