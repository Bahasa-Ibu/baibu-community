# Agents

Guidance for coding agents (and people) working in this repository.

## What this repository is

Baibu Community Edition: the open-source, white-label, self-hostable version
of the Baibu platform. It is public. Everything you write here (code,
comments, commit messages, issues, pull requests) is published.

## Rules

- **No private material.** Never reference, link or quote the private
  production codebase, its issues, people, production numbers or internal
  documents. Describe upstream syncs in general terms ("from the production
  deployment").
- **No real data.** Fixtures and tests use synthetic data only (`example.org`
  addresses, invented names). Never paste contributor text, chat transcripts
  or anything derived from them.
- **No proprietary or paid dependency.** Every runtime dependency must be
  under an OSI-approved licence and free to use. Third-party services go
  behind an adapter interface with a mock or console implementation; do not
  bundle vendor adapters. Do not recommend a language model.
- **English only.** Mark user-facing strings for translation (`gettext`,
  `{% translate %}`); deployments add languages.
- **Tests with every change.** Coverage must not go down. Run
  `docker compose run --rm django pytest` and `ruff check .` before pushing.
- **Pull requests only.** Branch from `main`, open a PR that closes its issue,
  fill in the template. Upstream syncs are labelled `upstream-sync` and add a
  row to `SYNC.md`.
- Keep the docs current: `docs/developer/configuration.md` for every new
  setting, `docs/developer/architecture.md` for new apps or models, and the
  test plan (`docs/qa/test-plan.md`) when a rule it states changes.

## Porting a feature from upstream

1. Read `SYNC.md`: the last synced reference and the deliberate differences.
2. Rewrite the feature to fit this codebase: same Django app names and file
   layout where possible (upstream `web-app/<path>` is `<path>` here), generic
   wording, settings instead of hard-coded values, adapters instead of vendor
   calls, English strings only.
3. Regenerate migrations here; never copy upstream migration files.
4. Add tests and docs, then add a row to `SYNC.md`.

## Commands

```sh
docker compose up --build                     # http://localhost:8000
docker compose --profile css up               # also rebuild CSS on template changes
docker compose run --rm django pytest
docker compose run --rm django ruff check . && docker compose run --rm django ruff format .
docker compose run --rm django python manage.py makemigrations
```

See `docs/developer/` for the architecture and configuration reference.
