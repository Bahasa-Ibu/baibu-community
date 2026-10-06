# One image for the web app, the Celery worker and Celery beat.
# Build targets: "development" (default in docker-compose.yml) and "production".

# --- CSS build ------------------------------------------------------------------
FROM node:22-bookworm-slim AS css
WORKDIR /app
COPY baibu/theme/static_src/package.json baibu/theme/static_src/package-lock.json baibu/theme/static_src/
RUN npm ci --prefix baibu/theme/static_src
COPY baibu baibu
COPY deployment deployment
RUN npm run build --prefix baibu/theme/static_src

# --- Python base ----------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS python-base
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/venv \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"
RUN apt-get update \
    && apt-get install --no-install-recommends -y gettext \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# --- Development: dev dependencies, source bind-mounted by Compose ---------------
FROM python-base AS development
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked
COPY . .
COPY --from=css /app/baibu/static/css/dist /opt/built-static/css/dist
ENV BUILT_STATIC_DIR=/opt/built-static
COPY compose/django/entrypoint compose/django/start-dev compose/django/celery-worker compose/django/celery-beat /usr/local/bin/
ENTRYPOINT ["entrypoint"]
CMD ["start-dev"]

# --- Production: no dev dependencies, static files collected, non-root ----------
FROM python-base AS production
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev
COPY . .
COPY --from=css /app/baibu/static/css/dist baibu/static/css/dist
COPY compose/django/entrypoint compose/django/start compose/django/celery-worker compose/django/celery-beat /usr/local/bin/
RUN DATABASE_URL="sqlite://:memory:" DJANGO_SETTINGS_MODULE=config.settings.test python manage.py collectstatic --noinput \
    && DATABASE_URL="sqlite://:memory:" DJANGO_SETTINGS_MODULE=config.settings.test python manage.py compilemessages --ignore=/venv \
    && addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p var/media var/private var/locale && chown -R app:app var
USER app
ENTRYPOINT ["entrypoint"]
CMD ["start"]
