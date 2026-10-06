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
| Migrations | Fresh history starting at `0001` | Upstream migrations are regenerated, not copied. |
| Layout | Django project at the repository root (upstream: `web-app/`) | Map `web-app/<path>` to `<path>`. |
