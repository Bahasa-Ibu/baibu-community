# Test plan

This document describes how Baibu Community Edition is tested: the testing
strategy, tools, coverage targets, sample test cases, the core data
structures under test and the pull request workflow.

The skeleton (stage 0), text submissions (stage 1), the assistant chat
(stage 2, in progress) and phone sign-in (from stage 3) are built. This plan
covers them and sets out how later stages will be tested. It is updated as
features land.

## Goals

- Catch regressions before they reach `main`.
- Protect the guarantees the platform makes to contributors: consent is
  recorded and never rewritten, deletion requests are tracked to completion,
  and personal data is not exposed.
- Keep tests fast and runnable offline, with no external accounts.
- Make test coverage visible to everyone.

## Testing strategy

Tests are organised in three layers.

| Layer | What it tests | Examples | Runs |
| --- | --- | --- | --- |
| Unit | A single function, model method, form or adapter, in isolation | Consent tier validation, text cleaning rules, settings helpers | Every pull request |
| Integration | Several parts working together through Django: views, models, the database, Celery tasks run eagerly, adapters | Sign-up flow writes a user and a consent record; a deletion request moves through its statuses | Every pull request |
| End-to-end | A user journey through the running application in a browser | Sign up, give consent, submit text, see it in the staff queue | Planned for stage 2; run before releases |

Most tests are unit and integration tests. End-to-end tests are kept few and
cover the main journeys only.

### What is mocked

Tests never call external services or the network.

| Dependency | In tests |
| --- | --- |
| Language models (LiteLLM) | Mocked. Tests patch the model call and return fixed responses, errors or timeouts. |
| Search, SMS and messaging, email, error reporting, speech-to-text | Mock or console adapters, the same ones used in local development. Email uses Django's in-memory backend. |
| Object storage | In-memory storage. The storage interface's own tests also run against a temporary directory and, in CI, a real open-source S3-compatible server (SeaweedFS). |
| Celery | Tasks run eagerly in the test process, or are called directly. |
| PostgreSQL | Real. Tests run against PostgreSQL, in the Compose stack and in CI, so that database behaviour matches production. |
| Time | Frozen or controlled where a test depends on dates or ordering. |

### Test data policy

Test data is synthetic only.

- Never use real personal data or real contributor text in tests, fixtures,
  screenshots or documentation. This includes data copied from any running
  deployment, even if anonymised.
- Create test data with factory-boy factories. Use obviously fake values
  (for example, addresses at `example.com`, phone numbers from reserved
  test ranges).
- Text samples for submission and chat tests are short passages written for
  the test.
- Test data is in English, or in clearly invented strings when a test needs
  non-English input (for example, to check Unicode handling).

## Tooling

| Tool | Use |
| --- | --- |
| pytest | Test runner |
| pytest-django | Django integration: database access, settings, client |
| factory-boy | Synthetic test data |
| coverage.py | Line and branch coverage |
| Ruff | Lint and import order |
| GitHub Actions | Runs lint, tests and coverage on every pull request and on `main` |

Commands:

```sh
docker compose run --rm django pytest
docker compose run --rm django coverage run -m pytest && docker compose run --rm django coverage report
docker compose run --rm django ruff check .
```

Tests use `config/settings/test.py`.

## Coverage

### Targets

| By end of | Target |
| --- | --- |
| Q2 | 15% |
| Q3 | 45% |
| Final (Q4) | 80% |

These are minimums for the whole codebase. New code should be well covered
from the start. A pull request must not lower total coverage.

### How coverage is published

CI measures coverage on every push to `main` and publishes the HTML report
on the documentation site under
[`coverage/`](https://bahasa-ibu.github.io/baibu-community/coverage/).
Anyone can see current coverage there without running the tests.

## Core data structures under test

The rules below are the intended behaviour. Where the code and this plan
differ, the difference is treated as a bug in one or the other and fixed in
the same pull request.

### Implemented

**User.** A person with an account. Signs in by email, and by phone when
`PHONE_SIGN_IN_ENABLED` is on. Has a profile.

- Email addresses are unique and compared case-insensitively.
- A user can see and edit only their own profile.
- Phone numbers are stored in E.164 format (`+` and 7 to 15 digits); input
  formatting (spaces, dashes, dots, brackets, a leading `00`) is removed,
  and numbers without a country code are refused.
- A phone number signs someone in only once it is verified with a code sent
  to it. A verified number belongs to one user; unverified numbers may
  repeat, and verifying a number removes it from accounts where it is still
  unverified.
- Asking for a sign-in code for an unknown or unverified number gives the
  same response as for a known number, and sends nothing.
- With phone sign-in off (the default), sign-in and sign-up behave as with
  email only, and the phone pages do not exist.

**ConsentRecord.** One entry in a user's consent history.

- Tiers:
    - `none`: no consent to use contributions;
    - `eval_only`: contributions may be used for evaluation only;
    - `training_eligible`: contributions may be used for evaluation and
      model training.
- Append-only. A change of consent creates a new record and stamps the
  previous one with the time it was revoked; nothing else about an existing
  record changes, and records are never deleted one by one. Deleting the
  user's account removes their history with it.
- Consent is recorded per scope (for example the whole platform, or chat),
  and each scope has its own history.
- A user's current consent is their most recent record. A user with no
  record, or whose latest record is revoked, is treated as `none`.
- Each record stores the tier, when it was given, where it was given and the
  version of the consent text the user saw (`CONSENT_TEXT_VERSION`).

**AccountDeletionRequest.** A user's request to delete their account and
data.

- Statuses: `submitted`, `approved`, `in_progress`, `completed`,
  `rejected`, `failed`.
- Allowed transitions:
    - `submitted` to `approved` or `rejected`;
    - `approved` to `in_progress`;
    - `in_progress` to `completed` or `failed`;
    - `failed` to `in_progress` (retry) or `rejected`.
- `completed` and `rejected` are final.
- Sending a request deactivates the account at once and signs the user out.
- A user can have only one open request (`submitted`, `approved`,
  `in_progress` or `failed`) at a time.
- When a request is completed, the requester's name, email and message are
  cleared; the request stays as a receipt, even after the account is deleted.

**White-label settings.** Platform name, tagline, contact address, enabled
languages, and a directory where a deployment can override templates and
translations.

**Submission** (stage 1). A text contribution from a user.

- Statuses: `pending`, `verified`, `needs_review`, `rejected`, `issue`.
- New submissions start as `pending`. Cleaning moves them to `verified`,
  `needs_review` or `issue`. Staff move `needs_review` to `verified` or
  `rejected`, `issue` to `rejected`, `verified` to `rejected`, and any
  cleaned submission back to `pending` to clean it again. Other changes are
  refused.
- Only users with at least `eval_only` consent can submit. The consent tier
  and record in force are stored with the submission.
- The same text (ignoring spacing) cannot be submitted twice.
- Raw and cleaned text are stored separately through the storage interface.
  The database holds only an excerpt of the cleaned text.
- If storage fails while submitting, nothing is recorded. If cleaning fails
  (cleaner error, missing raw text, storage error), the status is `issue`
  with the reason, and no cleaned file is left behind.
- Deleting a submission, or its user, deletes its stored files.
- A staff decision (accept or reject) records the reviewer and time and
  notifies the contributor once; a refused transition notifies nobody.

**ChatFlag and staff review.** A user's report of an assistant reply, and
the staff queues.

- Users can report only assistant replies in their own conversations, once
  per reply.
- Each queued item (submission or report) gets one decision; a second
  decision on the same item is refused and changes nothing.
- Only decisions allowed from the item's status are offered.
- Staff screens are for staff only: signed-out users are sent to sign in,
  other users get 403.

**Notification.** A message in a user's inbox.

- Users see only their own notifications. Opening one marks it read and
  follows its link only if the link is inside the platform.
- Registered kinds are translated when shown, not when created.
- Creating a notification never fails the caller.
- Read notifications past the retention period are deleted; unread ones
  are kept.

**Conversation, Message and Run** (stage 2). The assistant chat.

- A Conversation belongs to one user and holds an ordered list of Messages.
  Users choose a chat consent tier before their first conversation; the
  tier in force is recorded on the conversation.
- A Message is from the user or the assistant. The same idempotency key
  sent twice creates one message and one run.
- A Run is one attempt to generate an assistant reply. It records the
  model and prompt version used, its status and any error. A run is
  executed at most once. A failed Run can be retried; a retry creates a new
  Run and does not duplicate the user's message. After `CHAT_MAX_ATTEMPTS`
  attempts no further retry is allowed.
- A conversation has at most one queued or running run.
- Runs stuck beyond the timeout are failed; a reply arriving after that is
  discarded.
- Tools are offered only when configured. A tool failure is recorded and
  the reply still completes. Tool rounds are limited; only `http(s)` source
  links are shown.
- Prompt versions cannot be edited once saved; one version per name is
  active. Conversation events cannot be edited.

## Sample test cases

IDs use the area prefix and a number. "Planned" cases are written when the
feature lands.

| ID | Area | Preconditions | Steps | Expected |
| --- | --- | --- | --- | --- |
| TC-USR-01 | Sign-up | No account exists for `amina@example.com` | 1. Open the sign-up page. 2. Sign up with `amina@example.com`. 3. Follow the verification link in the email captured by the in-memory backend. | A User exists for the address, with the email verified. The user is signed in. Exactly one email was sent. |
| TC-USR-02 | Sign-up | A user exists for `amina@example.com` | Sign up again with `Amina@Example.com` | No second User is created. The response does not reveal whether the address is registered. |
| TC-CON-01 | Consent | Signed-in user with no consent record | Choose `eval_only` on the consent page and save | One ConsentRecord with tier `eval_only`, the current consent text version and a timestamp. Current consent is `eval_only`. |
| TC-CON-02 | Consent | User with a `training_eligible` record | Change consent to `none` | A second ConsentRecord with tier `none` is created. The first record keeps its tier and grant time and gains a revoked time. Current consent is `none`. History lists both, newest first. |
| TC-CON-03 | Consent | A ConsentRecord exists | Try to update or delete the record through the model layer and the admin | The update and delete are refused. The record is unchanged. |
| TC-DEL-01 | Deletion request | Signed-in user with no open deletion request | Submit a deletion request from the account page | An AccountDeletionRequest with status `submitted` exists. The user sees a confirmation with a receipt number and is signed out. The account is deactivated but not deleted yet. |
| TC-DEL-02 | Deletion request | User with a `submitted` request | Capture a second request for the same user (for example two requests sent at the same time) | No second request is created. The existing request is returned. |
| TC-DEL-03 | Deletion request | Request with status `submitted` | Try to move it straight to `completed` | The transition is refused. The status stays `submitted`. |
| TC-PHN-01 | Phone sign-in | Phone sign-in on, in-memory messaging provider. A user with verified number `+1 201 555 0123`. | 1. Request a sign-in code for `+1 201-555-0123`. 2. Enter the code from the recorded message. | One message was sent to `+12015550123`, containing a six-digit code and the platform name. The user is signed in. |
| TC-PHN-02 | Phone sign-in | Phone sign-in on. No verified account has `+44 7700 900123`; another account has it unverified. | Request a sign-in code for `+44 7700 900123` | The response is the same as for a known number (code page). No message is sent. |
| TC-PHN-03 | Phone sign-in | Phone sign-in on. Signed-in user without a phone number. | 1. Add `+1 201 555 0123` under Account, Phone. 2. Enter the code from the recorded message. | The number is stored as `+12015550123` and marked verified. |
| TC-PHN-04 | Phone sign-in | Phone sign-in on. Another user has `+1 201 555 0123` verified. | Add the same number to a second account and enter the code | Verification is refused. The second account has no number; the first keeps its verified number. |
| TC-PHN-05 | Phone sign-in | Phone sign-in on. The messaging provider raises `MessagingError`. | Request a sign-in code for a verified number | The user sees that the text could not be sent; no error page. The failure is logged with the number masked. |
| TC-PHN-06 | Phone sign-in | Phone sign-in off (default) | Open the sign-up page and `/accounts/phone/change/` | The sign-up form has no phone field. The phone page returns 404. |
| TC-WL-01 | White-label settings | Settings set the platform name to "Example Platform" and the contact address to `help@example.org` | Load the home page and the sign-in email | The page title, header and email use "Example Platform" and `help@example.org`. The default platform name does not appear in the title, header or email. |
| TC-WL-02 | White-label settings | A deployment override directory contains a replacement footer template | Load any page | The override footer is rendered instead of the default. |
| TC-STO-01 | File storage | Each backend in turn: in-memory, a temporary directory, an S3-compatible server | Save a JSON payload with non-Latin text under a key, read it back, save again under the same key, delete it | The payload reads back unchanged. The second save returns a different key and the first file is untouched. After deletion the key reads as missing. Private files on the filesystem have no URL. |
| TC-SUB-01 | Submission cleaning | User with `eval_only` consent | Submit text containing extra whitespace, control characters and a synthetic email address | Cleaned text has normalised whitespace, no control characters and the email address redacted. Raw text is stored separately. Status is `verified`, or `needs_review` if the cleaner flags it. The submission records consent tier `eval_only`. |
| TC-SUB-02 | Submission cleaning | Storage set to fail on write | Submit text | Status is `issue`. The error is logged. No partial cleaned file is left in storage. |
| TC-REV-01 | Staff review | Two submissions in `needs_review`; a signed-in staff member | Open the first, choose *Accept*, save | The first is `verified`, with the reviewer and time recorded; the contributor has one notification; the second submission opens next. |
| TC-REV-02 | Staff review | A report of an assistant reply; two staff members open it | Both choose a decision and save | The first decision is kept. The second reviewer is told it was already decided. The reporter has one notification. |
| TC-CHT-01 | Chat run retry | Conversation with one user message. The mocked model raises a timeout on the first call and returns "Hello" on the second. | 1. Send the message. 2. Retry the failed run. | First Run has status failed with the error recorded. A second Run succeeds. The conversation has one user message and one assistant message "Hello". |
| TC-CHT-02 | Chat run retry | Mocked model always raises an error | Send a message and retry up to the configured limit | Each attempt creates a Run. After the limit, no further retries are allowed and the user sees an error message. No assistant message is created. |

## Pull request workflow

Every change, including changes by maintainers, follows this workflow.

1. **Issue.** The change is described in a GitHub issue, in the relevant
   milestone where it applies. Small fixes can skip this.
2. **Branch.** Work happens on a branch off `main`, named as described in
   the [contributing guide](../community/contributing.md).
3. **Pull request.** The author opens a pull request against `main` and
   fills in the
   [pull request template](https://github.com/Bahasa-Ibu/baibu-community/blob/main/.github/PULL_REQUEST_TEMPLATE.md):
   summary, linked issue, type of change, how it was tested, and the
   checklist.
4. **CI green.** GitHub Actions runs lint, tests and coverage. All checks
   must pass. Coverage must not fall.
5. **Review.** At least one maintainer reviews and approves. The reviewer
   checks that the change has tests, that documentation is updated, and
   that no personal data or secrets are included.
6. **Squash merge.** A maintainer squash-merges the pull request. The
   pull request title becomes the commit message on `main`.

`main` is protected: direct pushes are blocked, and merging requires a
passing CI run and an approving review.

Pull requests labelled `upstream-sync` follow the same workflow.

## Release testing

Before each tagged release (from 1.0 onwards), maintainers will run the
full test suite, the end-to-end tests and a manual smoke test of the main
journeys on a fresh Compose stack. The release checklist will be added
before the first release.
