# Architecture

Baibu Community Edition is a Django monolith with Celery for background work.
It renders pages on the server (Django templates styled with Tailwind CSS);
there is no single-page JavaScript application.

## Services

```mermaid
flowchart LR
    Browser --> Django["Django (web)"]
    Django <--> Postgres[(PostgreSQL)]
    Django <--> Valkey[(Valkey)]
    Beat["Celery beat"] -- schedules --> Valkey
    Valkey -- tasks --> Worker["Celery worker"]
    Worker <--> Postgres
    Worker <--> Valkey
```

| Service | Role | Licence |
| --- | --- | --- |
| Django (Python 3.14) | Web application, admin, sign-in | BSD-3-Clause |
| PostgreSQL | All relational data | PostgreSQL Licence |
| Valkey | Cache, Celery broker. Any Redis-protocol server works. | BSD-3-Clause |
| Celery worker | Runs background tasks | BSD-3-Clause |
| Celery beat | Schedules periodic tasks (`CELERY_BEAT_SCHEDULE`) | BSD-3-Clause |

Every service is open source and needs no account with a third party.
Files live on the local filesystem or on any S3-compatible object store
([File storage](storage.md)). Later stages add a language-model endpoint
reached through LiteLLM, which the deployment chooses.

## Django apps

| App | Responsibility |
| --- | --- |
| `baibu.core` | Platform settings exposed to templates (`platform` context), language configuration, the file storage interface, the `/health/` endpoint, the worker heartbeat task, and keeping the Site record in line with the platform name and domain. |
| `baibu.users` | The user model (email sign-in, optional phone sign-in, one `name` field), profile completion, consent history, account deletion requests, the messaging provider interface for text messages, and the admin. |
| `baibu.submissions` | Text contributions: the submission form and list, the cleaning task and pluggable cleaners, and the admin used for review. See [Submissions and cleaning](submissions.md). |
| `baibu.chat` | The assistant chat: conversations, messages, runs, prompt versions, model variants, voice messages and the audit trail; the Celery tasks that transcribe voice messages and produce replies. See [Assistant chat](chat.md). |
| `baibu.notifications` | The in-app inbox, the unread count in the navigation and the `notify()` service other apps call. See [Notifications](notifications.md). |
| `baibu.staff` | The staff area: review queues for submissions and reported chat replies, and processing errors. No models of its own. See [Staff review](staff.md). |
| `baibu.localization` | Interface translations edited and published from the site: source string extraction, drafts, publishing with an audit trail, and loading published catalogues into running processes. See [Translations](translations.md). |
| `baibu.theme` | The Tailwind source. The built stylesheet is not committed. |

Sign-in, sign-up, email confirmation, password reset and two-factor
authentication come from [django-allauth](https://docs.allauth.org/). The
templates in `baibu/templates/allauth/` restyle its pages; they do not change
its behaviour. With `PHONE_SIGN_IN_ENABLED`, allauth also signs people in
with one-time codes sent to a verified phone number through the messaging
provider (`MESSAGING_PROVIDER`); see [Phone sign-in](phone-sign-in.md).

## Data model

```mermaid
erDiagram
    User ||--o{ ConsentRecord : "has history"
    User |o--o{ AccountDeletionRequest : "asks for"
    User ||--o{ Submission : contributes
    ConsentRecord |o--o{ Submission : "in force for"
    TranslationSource |o--o{ TranslationCatalogue : "merged into"
    TranslationPublication |o--o{ TranslationPublication : "restores"
    User {
        uuid id
        string email "unique, sign-in"
        string phone "E.164, optional"
        bool phone_verified "unique number when true"
        string name
        string city
        string country
    }
    ConsentRecord {
        uuid id
        string scope "e.g. platform, chat"
        string tier "none, eval_only, training_eligible"
        string source "where it was given"
        datetime granted_at
        datetime revoked_at "set when replaced"
        json metadata "locale, consent_text_version"
    }
    Submission {
        uuid id
        string language_code
        string status "pending, verified, needs_review, rejected, issue"
        string consent_tier "at submission"
        string raw_key "private storage"
        string clean_key "private storage"
        string content_hash "unique"
        text excerpt "of the cleaned text"
        string cleaner
        bool toxicity_detected
        int quality_score
    }
    User ||--o{ Conversation : has
    Conversation ||--o{ Message : contains
    Conversation ||--o{ Run : "replies by"
    Message ||--o{ Run : triggers
    Conversation ||--o{ ConversationEvent : "audit trail"
    Run ||--o{ ToolInvocation : calls
    Message ||--o{ ChatFlag : "reported in"
    Message ||--o| AudioClip : "voice recording"
    Conversation {
        uuid id
        string title
        string consent_tier "chat scope, at start"
        datetime last_activity_at
    }
    Message {
        uuid id
        string role "user, assistant"
        text content
        string idempotency_key
    }
    Run {
        uuid id
        string status "queued, running, completed, failed"
        int attempt
        string model_name
        string prompt_version
        json error
    }
    ChatFlag {
        uuid id
        string reason "harmful, incorrect, other"
        string status "open, confirmed, dismissed"
        datetime decided_at
    }
    AudioClip {
        uuid id
        string storage_key "private storage"
        string content_type
        int size_bytes
        float duration_seconds
        string status "pending, transcribing, transcribed, failed"
        int attempt
        string provider
        json error
    }
    ToolInvocation {
        uuid id
        string tool_name "internet_search"
        string provider
        string status "completed, failed"
        json arguments
        int result_count
    }
    User ||--o{ Notification : receives
    Notification {
        uuid id
        string kind "translated when shown"
        json params
        string link "internal path"
        datetime read_at
    }
    AccountDeletionRequest {
        uuid id
        string status
        string source
        datetime requested_at
        datetime completed_at
    }
    TranslationSource {
        uuid id
        string pot_key "private storage"
        string content_hash
        int entry_count
        datetime created_at
    }
    TranslationCatalogue {
        int id
        string language_code "unique"
        string draft_key "private storage"
        datetime updated_at
    }
    TranslationPublication {
        uuid id
        string language_code
        int version "per language"
        string po_key "private storage"
        string mo_key "private storage"
        int translated_count
        int fuzzy_count
        datetime published_at
    }
```

Primary keys are UUIDv7, so they sort by creation time and do not reveal
counts.

### Phone numbers

`User.phone` holds a number in E.164 format (`+12015550123`), or null.
Only a verified number signs anyone in, and a verified number belongs to
one user (a conditional unique constraint). Unverified numbers may repeat,
so typing someone else's number blocks nothing; verifying a number clears
it from accounts where it is still unverified.

### Consent

A consent decision is one `ConsentRecord`. Records are append-only: a new
decision adds a row and stamps the previous one with `revoked_at`. The model
refuses edits and single deletes, and the admin is read-only. Code reads
consent through `baibu.users.consent`:

- `consent_state(user=..., scope=...)` returns the current tier, with
  `allows(tier)` for checks. No record, or a revoked latest record, means
  `none`.
- `record_consent(user=..., tier=..., source=...)` records a change.
- `@consent_required(tier)` protects a view; users without enough consent are
  sent to the consent page.

Tiers are ordered: `training_eligible` includes `eval_only`, which includes
`none`. Each feature that uses contributions records under its own `scope`.

### Translations

`TranslationSource` rows are the extracted source strings (newest is
current), `TranslationCatalogue` holds one draft per language, and
`TranslationPublication` is the append-only audit trail: one row per publish
or restore, with who, when and counts. The newest publication of a language
is live. Each row's `published_by`, `created_by` or `updated_by` is cleared if
that user is deleted. See [Translations](translations.md).

### Account deletion

Sending a deletion request deactivates the account at once and signs the
user out. Staff then move the request through `submitted` → `approved` →
`in_progress` → `completed` (or `rejected`, or `failed` and retry). The admin
enforces these transitions. Completing a request clears the requester's
name, email and message. Deleting the user in the admin removes their
consent history; the request stays, without personal details, as a receipt.

New requests are emailed to the active members of the `operations-email`
group, or to `DJANGO_ADMINS` if the group is empty. The email contains only
the receipt number, source and time, never personal details.

## Requests and background work

- Every page goes through `TranslationSyncMiddleware` (loads newly published
  translations; see [Translations](translations.md)), then `LocaleMiddleware`
  (language from the URL prefix or the language switcher) and `ProfileCompletionMiddleware` (signed-in users
  missing a field in `PROFILE_REQUIRED_FIELDS` are sent to complete their
  profile; sign-in pages, terms, privacy and the admin for staff are exempt).
- Creating a submission queues `baibu.submissions.tasks.clean_submission`
  once the database transaction commits.
- Sending a chat message queues `baibu.chat.tasks.execute_run`; beat runs
  `baibu.chat.tasks.sweep_runs` every minute to recover stuck replies.
- Before each Celery task, the worker loads newly published translations in
  the same way, so emails sent from tasks use them.
- Sending a voice message queues `baibu.chat.tasks.transcribe_audio`, which
  queues `execute_run` once the transcript is in; beat runs
  `baibu.chat.tasks.sweep_transcriptions` every minute to recover stuck
  transcriptions.
- Celery beat sends `baibu.core.tasks.heartbeat` every minute. The worker
  stores the time in the cache, and `/health/` reports the worker as `ok`,
  `stale` or `unknown`. `/health/` returns HTTP 503 only if the database or
  cache is down, so a stopped worker does not restart the web container.

## URLs

The default language has no URL prefix (`/accounts/login/`); other enabled
languages are prefixed (`/fr/accounts/login/`). `/health/` and `/i18n/` are
never prefixed.

| Path | Page |
| --- | --- |
| `/` | Home |
| `/privacy/`, `/terms/` | Placeholders; every deployment replaces them |
| `/accounts/...` | Sign-in, sign-up, email, password, two-factor (allauth) |
| `/accounts/phone/change/`, `/accounts/phone/verify/` | Add, change and verify a phone number (only with `PHONE_SIGN_IN_ENABLED`) |
| `/users/account/` | Profile |
| `/users/account/consent/` | Consent choice and history |
| `/users/account/delete/` | Account deletion request |
| `/contribute/` | The user's submissions |
| `/contribute/new/` | Submit text |
| `/chat/` | Conversations and a new chat |
| `/notifications/` | The user's notifications |
| `/chat/replies/<id>/report/` | Report an assistant reply |
| `/staff/` | Staff overview, review queues (`review/submissions/`, `review/chats/`) and `errors/` |
| `/chat/consent/` | Chat consent choice |
| `/chat/<id>/` | One conversation |
| `/translations/` | Translations overview (translators only) |
| `/translations/<code>/` | Translate one language: edit, upload, download, publish |
| `/translations/<code>/history/` | Published versions and restore |
| `/chat/voice/`, `/chat/<id>/voice/` | Voice message upload (only with `CHAT_STT_PROVIDER` set) |
| `/chat/audio/<id>/` | Play back one's own recording |
| `/admin/` | Django admin (path set by `DJANGO_ADMIN_URL`) |
| `/health/` | Health check (JSON) |
