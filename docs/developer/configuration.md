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
| `DJANGO_MEDIA_ROOT` | `var/media` | Where uploaded files are stored. |
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
| `DEPLOYMENT_DIR` | `deployment/` | Directory with the deployment's `templates/`, `locale/` and `static/`. |

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
