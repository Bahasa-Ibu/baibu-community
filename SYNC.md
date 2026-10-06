# Sync log

Some core features are brought across from Baibu's production deployment, a
separate private codebase, by hand and from time to time, with no fixed
schedule. This file records where each sync left off so the next one can
start from there, and lists deliberate differences so they are not "fixed"
by accident.

Each sync is a public pull request labelled `upstream-sync`. Code is
rewritten for this repository rather than copied; contributor data,
production content, prompts and vendor integrations never come across.

## Syncs

| Date | Upstream reference | Pull request | What came across |
| --- | --- | --- | --- |
| 2026-10-06 | production `main` as of 2026-10-05 | #7 skeleton | Account model, append-only consent records, account deletion requests, profile completion. Rewritten for the Community Edition. |
| 2026-10-06 | production `main` as of 2026-10-05 | storage (#14), submissions (#13) | Text submission intake, raw and cleaned copies in private storage, statuses, duplicate refusal, deletion of stored files. Redesigned rather than ported: see the differences below. |
| 2026-10-06 | production `main` as of 2026-10-05 | chat (#15), search (#16) | Conversations, idempotent sends, runs on Celery, retries, prompt versions, model variants, audit trail; the `internet_search` tool with sources. Redesigned rather than ported. |

## Deliberate differences

| Area | Community Edition | Why |
| --- | --- | --- |
| Hosting | Docker Compose, Celery worker and beat | No dependency on any cloud provider. |
| Hosts | One host; chat will live under a path | Simpler to run. |
| Sign-in | Email (allauth). Optional phone sign-in (#23, off by default): allauth's phone support with one-time codes sent through a `MessagingProvider` interface; console and in-memory providers only; email stays required | No commercial messaging or chat-app provider bundled; deployments write their own provider. |
| Languages | English only; deployments add their own | White-label. |
| Profile | Required fields set by `PROFILE_REQUIRED_FIELDS`; the phone number is a sign-in method, not a profile field | Requirements differ per deployment. |
| Consent | Generic scopes and a consent page in account settings; `CONSENT_TEXT_VERSION` stored | Each feature records under its own scope. |
| Deletion requests | Strict status transitions; personal details cleared on completion; receipt kept after the user is deleted | Data minimisation. |
| Theme | Neutral Tailwind theme, runtime brand colour, system fonts | White-label; no externally hosted fonts. |
| File storage | One interface over the local filesystem or any S3-compatible store; records keep storage keys, not URIs | No cloud provider SDK in feature code. |
| Submission cleaning | A Celery task: built-in rules, then a pluggable cleaner (rules only by default, any model through LiteLLM, or a mock) | Runs with the Compose stack alone; no cloud workflow service and no bundled model. |
| Submission fields | Language as a code from settings; no tone or topic tags; the database keeps an excerpt of the cleaned text only | Simpler, and less personal data in the database. |
| Submission review | Django admin actions with enforced status transitions until the review queue (#17) | Smallest useful review tool. |
| Chat | Web chat only; replies through LiteLLM with a local `mock` model by default; API keys referenced by environment variable name; versioned prompts edited in the admin; one active reply per conversation; a sweeper instead of execution leases | Vendor-neutral and simpler to operate. |
| Web search | A `SearchProvider` interface with a mock; no provider bundled | No commercial search service in the code. |
| Interface translations | Edited and published on the site by translators holding a permission; drafts and published catalogues kept through the storage interface; source strings extracted with gettext into a temporary directory; each web and worker process loads new publications from storage when the cache signals one, with no third-party translation tool | Works on any storage backend and with several processes or containers, needs no writable code directory and no redeploy |
| Voice input | Off by default; a `SpeechToText` interface with a LiteLLM implementation (any transcription model or self-hosted compatible server) and a mock; recordings in private storage; transcription as a Celery task that then queues the reply; the conversation is busy while transcribing | No bundled speech service or model; same storage and run rules as the rest of chat. |
| Migrations | Fresh history starting at `0001` | Upstream migrations are regenerated, not copied. |
| Layout | Django project at the repository root (upstream: `web-app/`) | Map `web-app/<path>` to `<path>`. |
