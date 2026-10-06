# Phone sign-in

People can sign in with a one-time code sent to their phone, alongside
email. The code reaches the phone through a **messaging provider**, a small
class the deployment chooses. The platform ships a console provider for
development and an in-memory one for tests; it bundles no SMS or chat-app
vendor. Phone sign-in is off by default.

Sign-in, verification and rate limiting come from
[django-allauth's phone support](https://docs.allauth.org/en/latest/account/phone.html);
the platform supplies the storage (`User.phone`, `User.phone_verified`),
number validation and the messaging provider.

## Turning it on

```sh
# .env
PHONE_SIGN_IN_ENABLED=True
MESSAGING_PROVIDER=yourpackage.messaging.YourProvider
# Optional: ask for a phone number at sign-up as well.
PHONE_SIGN_UP_REQUIRED=False
```

With `PHONE_SIGN_IN_ENABLED=True`:

- The sign-in page accepts an email address **or** a phone number, with a
  password. "Send me a sign-in code" offers both, and sends the code by
  email or text message.
- The sign-up form has a phone field: optional, or required with
  `PHONE_SIGN_UP_REQUIRED=True`. Email stays required, so the existing email
  confirmation and password reset keep working.
- A new number is confirmed with a code before it counts: after sign-up,
  and when someone adds or changes a number under **Account → Phone**
  (`/accounts/phone/change/`).
- Only a **verified** number signs anyone in. Unverified numbers may appear
  on more than one account, so nobody can block a number by typing it
  first; verifying a number removes it from other accounts where it is
  still unverified. A verified number belongs to one account only.

With it off (the default), sign-in works exactly as before and no phone
page or field is shown. The `phone` columns exist either way, so a
deployment can switch it on later without a migration.

## Phone numbers

Numbers are stored in international (E.164) format: `+`, the country code,
then the number, 7 to 15 digits in all, for example `+12015550123`. Spaces,
dashes, dots, brackets and slashes are removed, and a leading `00` becomes
`+`. Numbers without a country code are refused rather than guessed. The
logic is in `baibu.users.phone`.

## Codes

| | |
| --- | --- |
| Format | Six digits (`ACCOUNT_PHONE_VERIFICATION_CODE_FORMAT`) |
| Valid for | 15 minutes to verify a number, 3 minutes to sign in (allauth defaults `ACCOUNT_PHONE_VERIFICATION_TIMEOUT`, `ACCOUNT_LOGIN_BY_CODE_TIMEOUT`) |
| Wrong guesses | 3 per code, then the code is discarded (`ACCOUNT_PHONE_VERIFICATION_MAX_ATTEMPTS`, `ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS`) |
| New code | Up to two resends while verifying a number (`ACCOUNT_PHONE_VERIFICATION_SUPPORTS_RESEND`) |

The text is the template `users/messages/verification_code.txt`, which a
deployment can override or translate like any other template
([White-label deployments](white-label.md)). Keep it short: one SMS segment
is 160 characters in the GSM alphabet, 70 otherwise.

## Rate limits

Text messages cost money and invite abuse, so code sending is rate limited
by allauth (`ACCOUNT_RATE_LIMITS`). The defaults:

| Action | Limit |
| --- | --- |
| `request_login_code` | 20 a minute per IP address, 3 a minute per phone number |
| `verify_phone` | 1 every 30 seconds per phone number, 3 a minute per IP address |
| `change_phone` | 1 a minute per user |
| `login_failed` | 10 a minute per IP address, 5 per 5 minutes per account |

Rate limits are counted in the cache (Valkey), so they hold across web
workers. A deployment can tighten them by setting `ACCOUNT_RATE_LIMITS` in
its settings. Your provider's own limits and fraud controls (for example,
allowed destination countries) are a second line of defence.

To avoid revealing which numbers have accounts, asking for a code for an
unknown or unverified number looks the same as for a known one, and sends
nothing.

## Writing a messaging provider

Subclass `baibu.users.messaging.MessagingProvider` and implement
`send_text(phone, text)`. Raise `MessagingError` when the message could not
be sent: the person sees "We could not send a text message" instead of an
error page, and the failure is logged with the number masked.

```python
# yourpackage/messaging.py
import json
import os
import urllib.request

from baibu.users.messaging import MessagingError
from baibu.users.messaging import MessagingProvider


class ExampleGatewayProvider(MessagingProvider):
    """Sends texts through an HTTP gateway. Replace with your vendor's API."""

    name = "example-gateway"

    def send_text(self, phone: str, text: str) -> None:
        request = urllib.request.Request(
            os.environ["EXAMPLE_GATEWAY_URL"],
            data=json.dumps({"to": phone, "text": text}).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['EXAMPLE_GATEWAY_TOKEN']}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except OSError as exc:  # includes HTTP errors and timeouts
            raise MessagingError(type(exc).__name__) from exc
```

- The provider is called during the request, so use a short timeout.
- Do not log the text or the full number: the text contains a sign-in code.
- Read credentials from the environment, never from code.
- The provider can deliver by SMS, a chat app or anything else that reaches
  the number. The text is the same.
- Test it the way the platform's tests do: `MemoryMessagingProvider`
  records every message in `MemoryMessagingProvider.outbox`.

Make the module importable by the platform (for example, install it into
your image, or add it under `baibu/` in your fork) and set
`MESSAGING_PROVIDER` to the class's dotted path.

`python manage.py check --deploy` warns (`users.W001`) if phone sign-in is
on while `MESSAGING_PROVIDER` is still the console provider.

## Trying it locally

Set `PHONE_SIGN_IN_ENABLED=True` in `.env` and restart the stack. The
console provider writes each text, code included, to the `django` container
log. Use a number from a range reserved for fiction, such as
`+1 201 555 0123` or `+44 7700 900123`.
