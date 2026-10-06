# Developer documentation

This section is for people who change the code or run a deployment.

- [Architecture](architecture.md): the services, Django apps and data model,
  and how requests and background tasks flow.
- [Configuration reference](configuration.md): every environment variable.
- [White-label deployments](white-label.md): how to give a deployment its own
  name, look, languages and pages without changing the code.

To run the platform locally, start with [Getting started](../getting-started.md).
To send a change, read the [contributing guide](../community/contributing.md).

## Day-to-day commands

All commands run inside the `django` service.

| Task | Command |
| --- | --- |
| Start the stack | `docker compose up --build` |
| Rebuild the stylesheet as you edit templates | `docker compose --profile css up` |
| Run the tests | `docker compose run --rm django pytest` |
| Coverage | `docker compose run --rm django coverage run -m pytest && docker compose run --rm django coverage report` |
| Lint and format | `docker compose run --rm django ruff check . && docker compose run --rm django ruff format .` |
| Create migrations | `docker compose run --rm django python manage.py makemigrations` |
| Django shell | `docker compose run --rm django python manage.py shell` |
| Admin user | `docker compose run --rm django python manage.py createsuperuser` |

Without Docker you need Python 3.14, [uv](https://docs.astral.sh/uv/),
PostgreSQL and a Redis-protocol server. Set `DATABASE_URL` and `REDIS_URL`,
then use `uv run pytest`, `uv run python manage.py runserver`, and so on.

## Code layout

```text
config/              Django settings, URLs, Celery app, WSGI entry point
  settings/          base.py (shared), local.py, test.py, production.py
baibu/
  core/              platform settings in templates, health check, worker heartbeat
  users/             accounts, profile, consent history, account deletion requests
  theme/             Tailwind source (static_src/); builds static/css/dist/styles.css
  templates/         Django templates; allauth/ restyles the sign-in pages
  static/            images, built CSS
compose/django/      Dockerfile and container start scripts
deployment/          a deployment's own templates, translations and static files
docs/                this documentation site (MkDocs)
```

Feature apps (submissions, chat, staff, notifications, localization,
analytics) are added as later stages land; see the
[roadmap](../project/roadmap.md).
