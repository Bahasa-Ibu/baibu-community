"""Base settings shared by every environment.

Everything a deployment is expected to change is read from the environment;
see ``.env.example`` and the configuration reference in the docs.
"""

from pathlib import Path

import environ

from baibu.core.branding import build_languages
from baibu.core.branding import register_extra_languages
from baibu.core.storage_config import S3Options
from baibu.core.storage_config import build_storages
from baibu.users.sign_in_config import login_methods
from baibu.users.sign_in_config import signup_fields

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
APPS_DIR = BASE_DIR / "baibu"
env = environ.Env()

if env.bool("DJANGO_READ_DOT_ENV_FILE", default=False):
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", default=False)
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True
SITE_ID = 1

# WHITE-LABEL
# ------------------------------------------------------------------------------
# A deployment sets its own name, contact address and languages, and may
# override any template, translation or static file by placing it under
# DEPLOYMENT_DIR (templates/, locale/, static/). See deployment/README.md.
PLATFORM_NAME = env("PLATFORM_NAME", default="Community Language Platform")
PLATFORM_TAGLINE = env(
    "PLATFORM_TAGLINE",
    default="Share your language, with consent, and help build tools that speak it.",
)
PLATFORM_CONTACT_EMAIL = env("PLATFORM_CONTACT_EMAIL", default="")
# Public host name, used in emails (for example links to confirm an address).
PLATFORM_DOMAIN = env("PLATFORM_DOMAIN", default="localhost:8000")
PLATFORM_LOGO_PATH = env("PLATFORM_LOGO_PATH", default="images/logo.svg")
PLATFORM_BRAND_COLOR = env("PLATFORM_BRAND_COLOR", default="")
DEPLOYMENT_DIR = Path(env("DEPLOYMENT_DIR", default=str(BASE_DIR / "deployment")))

# Language codes Django already knows (for example "en,fr,sw") need no more
# than PLATFORM_LANGUAGES. Languages Django does not ship, such as Javanese,
# are declared in PLATFORM_EXTRA_LANGUAGES as "code:English name:Local name"
# entries separated by semicolons.
PLATFORM_EXTRA_LANGUAGES = env("PLATFORM_EXTRA_LANGUAGES", default="")
register_extra_languages(PLATFORM_EXTRA_LANGUAGES)
LANGUAGE_CODE = env("PLATFORM_DEFAULT_LANGUAGE", default="en")
LANGUAGES = build_languages(env.list("PLATFORM_LANGUAGES", default=["en"]), default=LANGUAGE_CODE)
# English is the source language, so the project ships no catalogues; a
# deployment keeps its translations in DEPLOYMENT_DIR/locale.
LOCALE_PATHS = [str(DEPLOYMENT_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "allauth",
    "allauth.account",
    "allauth.mfa",
]
LOCAL_APPS = [
    "baibu.core",
    "baibu.users",
    "baibu.submissions",
    "baibu.chat",
    "baibu.notifications",
    "baibu.staff",
    "baibu.theme",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# AUTHENTICATION
# ------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_USER_MODEL = "users.User"
LOGIN_REDIRECT_URL = "users:account"
LOGIN_URL = "account_login"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "baibu.users.middleware.ProfileCompletionMiddleware",
]

# STATIC AND MEDIA
# ------------------------------------------------------------------------------
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = "/static/"
STATICFILES_DIRS = [str(DEPLOYMENT_DIR / "static"), str(APPS_DIR / "static")]
# The development image keeps a prebuilt stylesheet here so a fresh checkout is
# styled before the tailwind service has run; a local build takes precedence.
if BUILT_STATIC_DIR := env("BUILT_STATIC_DIR", default=""):
    STATICFILES_DIRS.append(BUILT_STATIC_DIR)
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]
MEDIA_ROOT = env("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "var" / "media"))
MEDIA_URL = "/media/"

# FILE STORAGE
# ------------------------------------------------------------------------------
# "local" keeps files on disk; "s3" uses any S3-compatible object store. Code
# stores contributor files through baibu.core.storage, never a vendor SDK.
STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")
# Contributor files (submitted text, audio). Never served over HTTP.
PRIVATE_MEDIA_ROOT = env("DJANGO_PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "var" / "private"))
STORAGES = build_storages(
    STORAGE_BACKEND,
    media_root=MEDIA_ROOT,
    private_root=PRIVATE_MEDIA_ROOT,
    s3=S3Options(
        bucket=env("S3_BUCKET", default=""),
        endpoint_url=env("S3_ENDPOINT_URL", default=""),
        region=env("S3_REGION", default=""),
        access_key_id=env("S3_ACCESS_KEY_ID", default=""),
        secret_access_key=env("S3_SECRET_ACCESS_KEY", default=""),
        addressing_style=env("S3_ADDRESSING_STYLE", default="path"),
        signed_url_seconds=env.int("S3_SIGNED_URL_SECONDS", default=3600),
    ),
)

# TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Deployment templates come first so they override the defaults.
        "DIRS": [str(DEPLOYMENT_DIR / "templates"), str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "baibu.core.context_processors.platform",
                "baibu.notifications.context_processors.notifications",
            ],
        },
    },
]
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# SECURITY
# ------------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_TIMEOUT = 5
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default=PLATFORM_CONTACT_EMAIL or "webmaster@localhost")
SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
EMAIL_SUBJECT_PREFIX = f"[{PLATFORM_NAME}] "

# ADMIN
# ------------------------------------------------------------------------------
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")
# Operational emails fall back to these addresses when the operations-email
# group is empty. Format: "Name <email>, Name <email>".
ADMINS = [
    (name.strip(), email.strip(" >"))
    for name, _, email in (entry.partition("<") for entry in env.list("DJANGO_ADMINS", default=[]))
    if email
]
MANAGERS = ADMINS
# Send the admin sign-in through allauth (rate limits, MFA).
DJANGO_ADMIN_FORCE_ALLAUTH = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(levelname)s %(asctime)s %(module)s %(process)d %(message)s"},
    },
    "handlers": {
        "console": {"level": "DEBUG", "class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}

# CACHE AND BROKER
# ------------------------------------------------------------------------------
# Any Redis-protocol server works. The Compose stack uses Valkey (BSD licence).
REDIS_URL = env("REDIS_URL", default="redis://valkey:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Cache outages must not take the site down.
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

# CELERY
# ------------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=None)
CELERY_TASK_IGNORE_RESULT = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# Periodic tasks run by Celery beat. Feature apps add their own entries.
CELERY_BEAT_SCHEDULE = {
    "worker-heartbeat": {
        "task": "baibu.core.tasks.heartbeat",
        "schedule": env.int("WORKER_HEARTBEAT_SECONDS", default=60),
    },
}
CELERY_BEAT_SCHEDULE["chat-sweep-runs"] = {
    "task": "baibu.chat.tasks.sweep_runs",
    "schedule": env.int("CHAT_SWEEP_SECONDS", default=60),
}
CELERY_BEAT_SCHEDULE["delete-old-notifications"] = {
    "task": "baibu.notifications.tasks.delete_old_notifications",
    "schedule": 24 * 60 * 60,
}
# The health endpoint reports the worker as stale after this many seconds
# without a heartbeat.
WORKER_HEARTBEAT_STALE_SECONDS = env.int("WORKER_HEARTBEAT_STALE_SECONDS", default=300)

# django-allauth
# ------------------------------------------------------------------------------
# Additional sign-in providers (any provider allauth supports) can be enabled
# by a deployment; none is enabled here.
ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", default=True)
# Phone sign-in is off by default. When on, people can add a phone number
# (verified by a code sent to it) and sign in with a one-time code sent to
# that number, alongside email. Codes go out through MESSAGING_PROVIDER.
PHONE_SIGN_IN_ENABLED = env.bool("PHONE_SIGN_IN_ENABLED", default=False)
# Ask for a phone number at sign-up (verified before the first sign-in).
PHONE_SIGN_UP_REQUIRED = env.bool("PHONE_SIGN_UP_REQUIRED", default=False)
ACCOUNT_LOGIN_METHODS = login_methods(phone=PHONE_SIGN_IN_ENABLED)
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SIGNUP_FIELDS = signup_fields(phone=PHONE_SIGN_IN_ENABLED, phone_required=PHONE_SIGN_UP_REQUIRED)
ACCOUNT_EMAIL_VERIFICATION = env("DJANGO_ACCOUNT_EMAIL_VERIFICATION", default="mandatory")
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_ADAPTER = "baibu.users.adapters.AccountAdapter"
ACCOUNT_FORMS = {"signup": "baibu.users.forms.UserSignupForm"}
# Phone sign-in: dotted path to a baibu.users.messaging.MessagingProvider.
# The console provider only writes messages to the log.
MESSAGING_PROVIDER = env("MESSAGING_PROVIDER", default="baibu.users.messaging.ConsoleMessagingProvider")
# Six digits: easy to type on any phone and picked up by SMS autofill.
ACCOUNT_PHONE_VERIFICATION_CODE_FORMAT = {"numeric": True, "dashed": False, "length": 6}
# Text messages get lost; allow two more codes per phone verification.
ACCOUNT_PHONE_VERIFICATION_SUPPORTS_RESEND = True

# PROFILE AND CONSENT
# ------------------------------------------------------------------------------
# Signed-in users missing any of these profile fields are asked to complete
# their profile before continuing. Allowed values: name, city, country.
PROFILE_REQUIRED_FIELDS = env.list("PROFILE_REQUIRED_FIELDS", default=["name"])
# The consent scope recorded by the account settings page. Feature apps that
# need their own consent (for example chat) record under their own scope.
CONSENT_DEFAULT_SCOPE = env("CONSENT_DEFAULT_SCOPE", default="platform")
# Stored with every consent decision. Change it whenever the wording people
# agree to (consent page or privacy notice) changes.
CONSENT_TEXT_VERSION = env("CONSENT_TEXT_VERSION", default="1")

# ACCOUNT DELETION
# ------------------------------------------------------------------------------
ACCOUNT_DELETION_REQUEST_RATE_LIMIT = env.int("ACCOUNT_DELETION_REQUEST_RATE_LIMIT", default=3)
ACCOUNT_DELETION_REQUEST_RATE_WINDOW_SECONDS = env.int("ACCOUNT_DELETION_REQUEST_RATE_WINDOW_SECONDS", default=3600)

# SUBMISSIONS
# ------------------------------------------------------------------------------
# Languages people may contribute in. Defaults to the interface languages; any
# code Django knows or PLATFORM_EXTRA_LANGUAGES declares is allowed.
SUBMISSION_LANGUAGES = env.list("SUBMISSION_LANGUAGES", default=[code for code, _name in LANGUAGES])
# Contributors need at least eval_only consent under this scope.
SUBMISSION_CONSENT_SCOPE = env("SUBMISSION_CONSENT_SCOPE", default=CONSENT_DEFAULT_SCOPE)
SUBMISSION_MIN_WORDS = env.int("SUBMISSION_MIN_WORDS", default=10)
SUBMISSION_MAX_CHARACTERS = env.int("SUBMISSION_MAX_CHARACTERS", default=20000)
# Characters of cleaned text kept in the database and shown to the contributor.
SUBMISSION_EXCERPT_LENGTH = env.int("SUBMISSION_EXCERPT_LENGTH", default=280)
# The cleaning step after the built-in rules: RuleCleaner (rules only, the
# default), LiteLLMCleaner (a model the deployment chooses) or MockCleaner.
SUBMISSION_CLEANER = env("SUBMISSION_CLEANER", default="baibu.submissions.cleaners.RuleCleaner")
# For LiteLLMCleaner: any model name LiteLLM accepts, and optionally the
# endpoint and key (for example a self-hosted OpenAI-compatible server).
SUBMISSION_CLEANER_MODEL = env("SUBMISSION_CLEANER_MODEL", default="")
SUBMISSION_CLEANER_API_BASE = env("SUBMISSION_CLEANER_API_BASE", default="")
SUBMISSION_CLEANER_API_KEY = env("SUBMISSION_CLEANER_API_KEY", default="")
SUBMISSION_CLEANER_TIMEOUT = env.int("SUBMISSION_CLEANER_TIMEOUT", default=60)
# Texts a cleaner scores below this (0-100) go to staff review.
SUBMISSION_MIN_QUALITY = env.int("SUBMISSION_MIN_QUALITY", default=50)

# CHAT
# ------------------------------------------------------------------------------
CHAT_ENABLED = env.bool("CHAT_ENABLED", default=True)
# Consent scope for conversations. Users choose a tier once before chatting.
CHAT_CONSENT_SCOPE = env("CHAT_CONSENT_SCOPE", default="chat")
# Model used when no model variant is marked as default in the admin. "mock"
# answers locally without any model; any LiteLLM model name works.
CHAT_MODEL = env("CHAT_MODEL", default="mock")
CHAT_MODEL_TIMEOUT = env.int("CHAT_MODEL_TIMEOUT", default=60)
# Earlier messages sent to the model with each new one.
CHAT_CONTEXT_MESSAGES = env.int("CHAT_CONTEXT_MESSAGES", default=20)
CHAT_MAX_MESSAGE_CHARACTERS = env.int("CHAT_MAX_MESSAGE_CHARACTERS", default=4000)
# Attempts at a reply to one message, including retries.
CHAT_MAX_ATTEMPTS = env.int("CHAT_MAX_ATTEMPTS", default=3)
# A reply still running after this long is failed so the user can retry.
CHAT_RUN_TIMEOUT_SECONDS = env.int("CHAT_RUN_TIMEOUT_SECONDS", default=180)
# Web search for the assistant's internet_search tool: a SearchProvider
# subclass (see baibu.chat.search). Empty disables the tool. No provider is
# bundled; baibu.chat.search.MockSearchProvider returns made-up results.
CHAT_SEARCH_PROVIDER = env("CHAT_SEARCH_PROVIDER", default="")
CHAT_SEARCH_MAX_RESULTS = env.int("CHAT_SEARCH_MAX_RESULTS", default=5)
# Rounds of tool calls the model may make before it must answer.
CHAT_MAX_TOOL_ROUNDS = env.int("CHAT_MAX_TOOL_ROUNDS", default=2)

# NOTIFICATIONS
# ------------------------------------------------------------------------------
NOTIFICATIONS_ENABLED = env.bool("NOTIFICATIONS_ENABLED", default=True)
# Read notifications older than this are deleted daily.
NOTIFICATIONS_RETENTION_DAYS = env.int("NOTIFICATIONS_RETENTION_DAYS", default=180)
