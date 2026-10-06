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
| Sign-in | Email (allauth). Phone sign-in will use a messaging adapter interface (#23) | No commercial messaging provider bundled. |
| Languages | English only; deployments add their own | White-label. |
| Profile | Required fields set by `PROFILE_REQUIRED_FIELDS`; no phone field yet | Requirements differ per deployment. |
| Consent | Generic scopes and a consent page in account settings; `CONSENT_TEXT_VERSION` stored | Each feature records under its own scope. |
| Deletion requests | Strict status transitions; personal details cleared on completion; receipt kept after the user is deleted | Data minimisation. |
| Theme | Neutral Tailwind theme, runtime brand colour, system fonts | White-label; no externally hosted fonts. |
| File storage | One interface over the local filesystem or any S3-compatible store; records keep storage keys, not URIs | No cloud provider SDK in feature code. |
| Submission cleaning | A Celery task: built-in rules, then a pluggable cleaner (rules only by default, any model through LiteLLM, or a mock) | Runs with the Compose stack alone; no cloud workflow service and no bundled model. |
| Submission fields | Language as a code from settings; no tone or topic tags; the database keeps an excerpt of the cleaned text only | Simpler, and less personal data in the database. |
| Submission review | Django admin actions with enforced status transitions until the review queue (#17) | Smallest useful review tool. |
| Chat | Web chat only; replies through LiteLLM with a local `mock` model by default; API keys referenced by environment variable name; versioned prompts edited in the admin; one active reply per conversation; a sweeper instead of execution leases | Vendor-neutral and simpler to operate. |
| Web search | A `SearchProvider` interface with a mock; no provider bundled | No commercial search service in the code. |
| Migrations | Fresh history starting at `0001` | Upstream migrations are regenerated, not copied. |
| Layout | Django project at the repository root (upstream: `web-app/`) | Map `web-app/<path>` to `<path>`. |
