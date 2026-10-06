# Configuration reference

All configuration comes from environment variables. For local development,
copy `.env.example` to `.env`; Docker Compose passes it to every service.
`config.settings.production` refuses to start without the variables marked
**required**.

## Django

| Variable | Default | Meaning |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.local` (manage.py), `config.settings.production` (WSGI, Celery) | Which settings module to load. |
| `DJANGO_SECRET_KEY` | **required** in production | Django's secret key. Use a long random value. |
| `DJANGO_ALLOWED_HOSTS` | **required** in production | Comma-separated host names the site answers to. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://localhost:8000` (local) | Comma-separated origins allowed to post forms, e.g. `https://lugha.example.org`. |
| `DJANGO_DEBUG` | `False` | Debug mode. `local` settings always enable it. |
| `DJANGO_TIME_ZONE` | `UTC` | Time zone for display and scheduling. |
| `DJANGO_ADMIN_URL` | `admin/` | Path of the Django admin. Changing it reduces automated probing. |
| `DJANGO_ADMINS` | empty | `Name <email>, Name <email>`: fallback recipients for operational email. |
| `DJANGO_ADMIN_FORCE_ALLAUTH` | `False` (`True` in production) | Send admin sign-in through allauth, so rate limits and two-factor apply. |
| `DJANGO_READ_DOT_ENV_FILE` | `False` | Read `.env` from the project root without Docker. |
| `DJANGO_SECURE_SSL_REDIRECT` | `True` (production) | Redirect HTTP to HTTPS. Set `False` only if the proxy already does. |
| `DJANGO_SECURE_HSTS_SECONDS` | `60` (production) | HSTS max-age. Raise it once HTTPS works. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` (production) | HSTS for subdomains. |
| `DJANGO_SECURE_HSTS_PRELOAD` | `True` (production) | HSTS preload flag. |
| `CONN_MAX_AGE` | `60` (production) | Seconds to keep database connections open. |
| `GUNICORN_WORKERS` | `3` | Web worker processes in the production image. |

## Your platform (white-label)

See [White-label deployments](white-label.md) for how these fit together.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PLATFORM_NAME` | `Community Language Platform` | Shown in the header, page titles, footer and emails. |
| `PLATFORM_TAGLINE` | a generic sentence | Shown on the home page and in the page description. |
| `PLATFORM_CONTACT_EMAIL` | empty | Public contact address; also the default sender of emails. |
| `PLATFORM_DOMAIN` | `localhost:8000` | Public host name, used in links inside emails. |
| `PLATFORM_LOGO_PATH` | `images/logo.svg` | Static path of the logo and favicon. Put your file in `deployment/static/`. |
| `PLATFORM_BRAND_COLOR` | empty (teal) | Any CSS colour, e.g. `#7c3aed`. Applied without rebuilding the stylesheet. |
| `PLATFORM_LANGUAGES` | `en` | Comma-separated language codes offered to users. |
| `PLATFORM_DEFAULT_LANGUAGE` | `en` | Language for URLs without a prefix. Must be in `PLATFORM_LANGUAGES`. |
| `PLATFORM_EXTRA_LANGUAGES` | empty | Languages Django does not know: `code:English name:Local name;...`. |
| `DEPLOYMENT_DIR` | `deployment/` | Directory with the deployment's `templates/`, `locale/` and `static/`. Translations published from the site take precedence over `locale/` ([Translations](translations.md)). |

## Accounts and consent

| Variable | Default | Meaning |
| --- | --- | --- |
| `DJANGO_ACCOUNT_ALLOW_REGISTRATION` | `True` | Allow new sign-ups. |
| `DJANGO_ACCOUNT_EMAIL_VERIFICATION` | `mandatory` | `mandatory`, `optional` or `none` (allauth). |
| `PROFILE_REQUIRED_FIELDS` | `name` | Profile fields users must fill in: any of `name`, `city`, `country`. |
| `CONSENT_DEFAULT_SCOPE` | `platform` | Scope recorded by the consent page. |
| `CONSENT_TEXT_VERSION` | `1` | Stored with each consent decision. Change it whenever the consent wording or privacy notice changes. |
| `ACCOUNT_DELETION_REQUEST_RATE_LIMIT` | `3` | Deletion requests allowed per user per window. |
| `ACCOUNT_DELETION_REQUEST_RATE_WINDOW_SECONDS` | `3600` | Length of that window. |

## Phone sign-in

See [Phone sign-in](phone-sign-in.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `PHONE_SIGN_IN_ENABLED` | `False` | Let people add a verified phone number and sign in with a one-time code sent to it, alongside email. |
| `PHONE_SIGN_UP_REQUIRED` | `False` | With phone sign-in on: require a phone number at sign-up (verified before the first sign-in). Otherwise the field is optional. |
| `MESSAGING_PROVIDER` | `baibu.users.messaging.ConsoleMessagingProvider` | Class that sends text messages: `ConsoleMessagingProvider` (writes them to the log), `MemoryMessagingProvider` (tests) or your own. |

## File storage

See [File storage](storage.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `STORAGE_BACKEND` | `local` | `local` (filesystem) or `s3` (any S3-compatible object store). |
| `DJANGO_MEDIA_ROOT` | `var/media` | `local`: where ordinary uploads are stored. |
| `DJANGO_PRIVATE_MEDIA_ROOT` | `var/private` | `local`: where contributor files are stored. Never served. |
| `S3_BUCKET` | **required** for `s3` | Bucket for both stores (prefixes `media/` and `private/`). Keep it private. |
| `S3_ENDPOINT_URL` | empty (the SDK default) | Endpoint of the S3-compatible server, e.g. `https://s3.example.org`. |
| `S3_REGION` | empty | Region name, if the server needs one. |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | empty | Credentials. Empty means the usual resolution (environment, instance role). |
| `S3_ADDRESSING_STYLE` | `path` | `path` or `virtual`. Most self-hosted servers need `path`. |
| `S3_SIGNED_URL_SECONDS` | `3600` | Lifetime of signed URLs for stored files. |

## Submissions

See [Submissions and cleaning](submissions.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `SUBMISSION_LANGUAGES` | the `PLATFORM_LANGUAGES` codes | Languages people may contribute in. Any code Django knows or `PLATFORM_EXTRA_LANGUAGES` declares. With one language, the form does not ask. |
| `SUBMISSION_CONSENT_SCOPE` | `CONSENT_DEFAULT_SCOPE` | Consent scope checked before contributing (at least `eval_only`). |
| `SUBMISSION_MIN_WORDS` | `10` | Shortest text accepted. |
| `SUBMISSION_MAX_CHARACTERS` | `20000` | Longest text accepted. |
| `SUBMISSION_EXCERPT_LENGTH` | `280` | Characters of cleaned text kept in the database and shown to the contributor. |
| `SUBMISSION_CLEANER` | `baibu.submissions.cleaners.RuleCleaner` | Cleaner run after the built-in rules: `RuleCleaner`, `LiteLLMCleaner`, `MockCleaner` or your own class. |
| `SUBMISSION_CLEANER_MODEL` | empty | `LiteLLMCleaner`: a model name LiteLLM accepts, e.g. `openai/<model>` for an OpenAI-compatible server. |
| `SUBMISSION_CLEANER_API_BASE` | empty | `LiteLLMCleaner`: endpoint URL, if the model needs one. |
| `SUBMISSION_CLEANER_API_KEY` | empty | `LiteLLMCleaner`: API key, if the endpoint needs one. |
| `SUBMISSION_CLEANER_TIMEOUT` | `60` | `LiteLLMCleaner`: seconds to wait for the model. |
| `SUBMISSION_MIN_QUALITY` | `50` | Texts a cleaner scores below this (0 to 100) go to review. |

## Chat

See [Assistant chat](chat.md). Models and prompts are managed in the admin.

| Variable | Default | Meaning |
| --- | --- | --- |
| `CHAT_ENABLED` | `True` | Offer the assistant chat. |
| `CHAT_CONSENT_SCOPE` | `chat` | Consent scope users choose before chatting. |
| `CHAT_MODEL` | `mock` | Model used when no model variant is the default. `mock` needs no model. |
| `CHAT_MODEL_TIMEOUT` | `60` | Seconds to wait for the model. |
| `CHAT_CONTEXT_MESSAGES` | `20` | Earlier messages sent to the model with each new one. |
| `CHAT_MAX_MESSAGE_CHARACTERS` | `4000` | Longest message accepted. |
| `CHAT_MAX_ATTEMPTS` | `3` | Attempts at one reply, including retries. |
| `CHAT_RUN_TIMEOUT_SECONDS` | `180` | A reply still running after this long is failed so the user can retry. |
| `CHAT_SWEEP_SECONDS` | `60` | How often beat checks for stuck replies. |
| `CHAT_SEARCH_PROVIDER` | empty (no search) | Dotted path of a `SearchProvider` subclass for the `internet_search` tool, e.g. `baibu.chat.search.MockSearchProvider`. |
| `CHAT_SEARCH_MAX_RESULTS` | `5` | Results per search. |
| `CHAT_MAX_TOOL_ROUNDS` | `2` | Rounds of tool calls before the model must answer. |
| `CHAT_TAGGING_ENABLED` | `False` | Tag idle conversations by topic, language and intent. |
| `CHAT_TAGGING_MIN_TIER` | `eval_only` | Lowest chat consent tier whose conversations are tagged. |
| `CHAT_TAGGING_MODEL` | empty (the chat's default model) | LiteLLM model for tagging. `mock` matches topic names as keywords. |
| `CHAT_TAGGING_INTENTS` | `question,advice,information,conversation,other` | Intents the tagger chooses from. |
| `CHAT_TAGGING_IDLE_MINUTES` | `30` | A conversation is tagged after this long without activity. |
| `CHAT_TAGGING_INTERVAL_SECONDS` | `600` | How often beat looks for conversations to tag. |
| `CHAT_TAGGING_BATCH_SIZE` | `100` | Conversations tagged per run. |
| `CHAT_TAGGING_MAX_TOPICS` | `3` | Topics per conversation. |
| `CHAT_TAGGING_MAX_MESSAGES`, `CHAT_TAGGING_MAX_CHARACTERS` | `40`, `12000` | How much of a conversation the tagger sees. |
| `CHAT_STT_PROVIDER` | empty (no voice input) | Dotted path of a `SpeechToText` subclass for voice messages: `baibu.chat.speech.LiteLLMSpeechToText`, `baibu.chat.speech.MockSpeechToText` (made-up transcripts) or your own. Empty turns voice input off. |
| `CHAT_STT_MODEL` | empty | `LiteLLMSpeechToText`: a transcription model name LiteLLM accepts, e.g. `openai/<model>` for an OpenAI-compatible server. |
| `CHAT_STT_API_BASE` | empty | `LiteLLMSpeechToText`: endpoint URL, if the model needs one. |
| `CHAT_STT_API_KEY_ENV` | empty | `LiteLLMSpeechToText`: **name** of the environment variable that holds the API key (the key itself is never a setting). |
| `CHAT_STT_TIMEOUT` | `60` | `LiteLLMSpeechToText`: seconds to wait for a transcript. |
| `CHAT_STT_PARAMETERS` | `{}` | `LiteLLMSpeechToText`: extra arguments for every call, as JSON, e.g. `{"language": "sw"}`. |
| `CHAT_VOICE_MAX_BYTES` | `10485760` (10 MiB) | Largest recording accepted. Set your reverse proxy's upload limit to match. |
| `CHAT_VOICE_MAX_SECONDS` | `120` | The browser stops recording and sends after this many seconds. |
| `CHAT_VOICE_CONTENT_TYPES` | `audio/webm,audio/ogg,audio/mp4,audio/x-m4a,audio/aac,audio/mpeg,audio/wav,audio/x-wav` | Audio formats accepted for upload (comma-separated). |

## Notifications

See [Notifications](notifications.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `NOTIFICATIONS_ENABLED` | `True` | Create in-app notifications. |
| `NOTIFICATIONS_RETENTION_DAYS` | `180` | Read notifications older than this are deleted daily. |

## Translations

See [Translations](translations.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOCALIZATION_PUBLISHED_DIR` | `var/locale` | Where each process keeps its copy of the published catalogues. Listed first in `LOCALE_PATHS`, so published translations win over `DEPLOYMENT_DIR/locale`. Must be writable; it need not be shared or backed up. |
| `LOCALIZATION_SYNC` | `True` | Load translations published from the `/translations/` pages into every web and worker process. Turn off only if you manage catalogues as files. |
| `LOCALIZATION_SYNC_SECONDS` | `10` | How often each process checks the cache for a new publication. `0` checks before every request and task. |

## Usage metrics

See [Usage metrics](metrics.md).

| Variable | Default | Meaning |
| --- | --- | --- |
| `METRICS_COMPUTE_HOUR` | `2` | Hour (0 to 23, in `DJANGO_TIME_ZONE`) at which beat computes the previous day's rollups. |
| `METRICS_COMPUTE_MINUTE` | `15` | Minute of that hour. |
| `METRICS_CATCH_UP_DAYS` | `7` | If the worker missed nights, the nightly task fills in up to this many days back. Use `compute_metrics` for more. |
| `METRICS_RETENTION_WEEKS` | `8` | Weeks after joining for which weekly retention is counted. |
| `METRICS_MIN_GROUP_SIZE` | `5` | Breakdowns by language or consent tier show counts from 1 up to this number minus one as `<N` on the usage page and in the CSV export. `0` or `1` turns this off. |
| `METRICS_MAX_RANGE_DAYS` | `366` | Longest date range the usage page and export accept. |

## Email

Any SMTP server works. Local development prints emails to the `django`
container log.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DJANGO_EMAIL_BACKEND` | SMTP (console in `local`) | Django email backend class. |
| `DJANGO_EMAIL_HOST` | `localhost` | SMTP server (production). |
| `DJANGO_EMAIL_PORT` | `587` | SMTP port. |
| `DJANGO_EMAIL_HOST_USER` | empty | SMTP user name. |
| `DJANGO_EMAIL_HOST_PASSWORD` | empty | SMTP password. |
| `DJANGO_EMAIL_USE_TLS` | `True` | Use STARTTLS. |
| `DJANGO_DEFAULT_FROM_EMAIL` | `PLATFORM_CONTACT_EMAIL` | Sender address. |
| `DJANGO_SERVER_EMAIL` | `DJANGO_DEFAULT_FROM_EMAIL` | Sender of error emails. |

## Database, cache and Celery

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | **required** | PostgreSQL URL, e.g. `postgres://user:pass@host:5432/db`. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | see `.env.example` | Used by the Compose `postgres` service to create the database. |
| `REDIS_URL` | `redis://valkey:6379/0` | Cache and default broker. Any Redis-protocol server. |
| `CELERY_BROKER_URL` | `REDIS_URL` | Celery broker. |
| `CELERY_RESULT_BACKEND` | none | Celery result backend; results are not stored by default. |
| `CELERY_CONCURRENCY` | `2` | Worker processes. |
| `CELERY_LOG_LEVEL` | `INFO` | Worker and beat log level. |
| `WORKER_HEARTBEAT_SECONDS` | `60` | How often beat schedules the heartbeat task. |
| `WORKER_HEARTBEAT_STALE_SECONDS` | `300` | After this long without a heartbeat, `/health/` reports the worker as `stale`. |

## Development image

| Variable | Default | Meaning |
| --- | --- | --- |
| `BUILT_STATIC_DIR` | `/opt/built-static` in the development image | A stylesheet built into the image, used until you build one locally. |
