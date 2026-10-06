# Getting started

This page explains how to run Baibu Community Edition on your own machine
for development or evaluation.

## Requirements

- Git
- Docker with Docker Compose

Everything else (Python, PostgreSQL, Valkey, Celery) runs in containers. You
do not need a language model endpoint or any third-party account to run the
platform locally. Mock and console adapters are used by default.

## Run the platform

```sh
git clone https://github.com/Bahasa-Ibu/baibu-community.git
cd baibu-community
cp .env.example .env
docker compose up --build        # app on http://localhost:8000
```

Open <http://localhost:8000> in a browser. Sign up, then confirm your email
address with the link printed in the `django` container log
(`docker compose logs django`). Local development prints emails instead of
sending them.

<http://localhost:8000/health/> reports whether the database, cache and
Celery worker are up. The worker shows as `unknown` for the first minute,
until Celery beat has scheduled its first heartbeat.

To change templates or styles, also start the stylesheet watcher:

```sh
docker compose --profile css up
```

The Compose stack starts the Django web application, PostgreSQL, Valkey, a
Celery worker and Celery beat. Commands that run inside the application use
the `django` service.

## Create an admin user

```sh
docker compose run --rm django python manage.py createsuperuser
```

## Run tests, coverage and lint

```sh
docker compose run --rm django pytest
docker compose run --rm django coverage run -m pytest && docker compose run --rm django coverage report
docker compose run --rm django ruff check .
```

See the [test plan](qa/test-plan.md) for the testing strategy.

## Configuration

Configuration is read from environment variables. `.env.example` lists them
with development defaults. Copy it to `.env` and edit it. Never commit
`.env`.

Django settings live in `config/settings/`:

| Module | Used for |
| --- | --- |
| `base.py` | Settings shared by every environment |
| `local.py` | Local development |
| `test.py` | The test suite |
| `production.py` | Deployments |

Every variable is listed in the [configuration reference](developer/configuration.md).
To give a deployment its own name, look, pages and languages, see
[White-label deployments](developer/white-label.md).

## Next steps

- Read the [contributing guide](community/contributing.md) if you want to
  change the code or documentation.
- Read the [project charter](project/charter.md) to understand what the
  project covers and how the name may be used.
