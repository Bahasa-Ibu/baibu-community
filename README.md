# Baibu Community Edition

[![CI](https://github.com/Bahasa-Ibu/baibu-community/actions/workflows/ci.yml/badge.svg)](https://github.com/Bahasa-Ibu/baibu-community/actions/workflows/ci.yml)
[![Docs](https://github.com/Bahasa-Ibu/baibu-community/actions/workflows/docs.yml/badge.svg)](https://bahasa-ibu.github.io/baibu-community/)
[![Coverage report](https://img.shields.io/badge/coverage-report-blue)](https://bahasa-ibu.github.io/baibu-community/coverage/)

An open-source, self-hostable, white-label platform for collecting community
language contributions and running an assistant chat in local languages.

Organisations can use it to stand up their own platform, in their own country
and languages, under their own name. The repository ships in English only.
Each deployment adds its own languages, branding, prompts and topics.

**Status: early.** The application skeleton runs: accounts, consent and
deletion requests on a Docker Compose stack, with tests. Feature stages
follow. Expect breaking changes until a 1.0 release.

## Features

Planned features are delivered in stages. Each stage is tracked in
[GitHub Issues](https://github.com/Bahasa-Ibu/baibu-community/issues).

| Stage | Features | Status |
| --- | --- | --- |
| 0. Skeleton | Docker Compose stack, email sign-in, profile, append-only consent history, account deletion requests, white-label settings | Done |
| 1. Submissions | Text submissions, cleaning pipeline, storage adapters (local filesystem, S3-compatible) | Done |
| 2. Chat and review | Assistant chat, staff review queue, notifications, translation workflow | Done |
| 3. Extensions | Voice input, usage metrics, conversation topic tagging, phone sign-in via a messaging adapter | Done |

What exists today: stage 0, the project documents, the documentation site
and the contribution process.

### Design principles

- **No proprietary dependencies.** Everything runs on open-source components:
  Django 5.2 on Python 3.14, PostgreSQL, Valkey (a BSD-licensed,
  Redis-compatible broker and cache), Celery worker and Celery beat, and local
  or S3-compatible object storage.
- **Bring your own model.** Language models are reached through
  [LiteLLM](https://github.com/BerriAI/litellm), so a deployment points the
  platform at the model endpoint of its choice. The project makes no model
  recommendation.
- **Adapters for third-party services.** Search, SMS and messaging, email,
  error reporting and speech-to-text sit behind adapter interfaces. The
  repository includes mock or console implementations only. Deployments add
  adapters for the vendors they use.
- **Consent is recorded, not assumed.** Contributors give explicit consent,
  and the consent history is append-only.

## Quick start

You need Git and Docker with Docker Compose.

```sh
git clone https://github.com/Bahasa-Ibu/baibu-community.git
cd baibu-community
cp .env.example .env
docker compose up --build        # app on http://localhost:8000
```

Emails, such as the link to confirm a new account, are printed in the
`django` container log. `http://localhost:8000/health/` reports whether the
database, cache and worker are up.

Create an admin user:

```sh
docker compose run --rm django python manage.py createsuperuser
```

Run tests, coverage and lint:

```sh
docker compose run --rm django pytest
docker compose run --rm django coverage run -m pytest && docker compose run --rm django coverage report
docker compose run --rm django ruff check .
```

## Configuration

Configuration is read from environment variables. `.env.example` lists them
with safe development defaults. Copy it to `.env` and edit. Never commit
`.env`.

Django settings live in `config/settings/` (`base`, `local`, `test`,
`production`). Every variable is listed in the
[configuration reference](https://bahasa-ibu.github.io/baibu-community/developer/configuration/),
and the [white-label guide](https://bahasa-ibu.github.io/baibu-community/developer/white-label/)
explains how to give a deployment its own name, look, pages and languages.

## Documentation

Documentation is published at
<https://bahasa-ibu.github.io/baibu-community/>. It includes the getting
started guide, the test plan, the roadmap and community documents. The
source is in [`docs/`](docs/).

## How this repository relates to Baibu

Baibu is a platform built by PT Ibu Punya Mimpi in Indonesia. Its production
deployment, [baibu.id](https://baibu.id), serves Indonesian mothers in
Indonesian, Javanese and Sundanese, and is run from a separate codebase.

This repository is the Community Edition: the open-source, reusable core of
the platform, without the production deployment's content, languages,
branding or vendor integrations. Maintainers occasionally bring core features
across from the production deployment by hand, in public pull requests
labelled `upstream-sync`. See the [project charter](PROJECT_CHARTER.md) for
the details.

Development of the Community Edition is supported by the UNICEF Venture Fund.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md) first. Report security issues privately
as described in [SECURITY.md](SECURITY.md), not in public issues.

## Licence and trademarks

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

Copyright 2026 PT Ibu Punya Mimpi.

The licence does not cover the "Baibu" and "Bahasa Ibu" names or logos.
Deployments must use their own name and branding. They may say they are
"built on Baibu Community Edition". See the
[charter](PROJECT_CHARTER.md#trademarks).
