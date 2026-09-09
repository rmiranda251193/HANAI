"""
Django settings for the HANAI / DodongOS Physics AI project.

One environment-driven settings module. Development and production differ only
by environment variables -- there is no second settings file to keep in sync.

    development   -> DJANGO_DEBUG=True, SQLite, relaxed security
    production    -> DJANGO_DEBUG=False, PostgreSQL via DATABASE_URL, HTTPS
                     security headers, WhiteNoise static, structured logging

See ``.env.example`` for every supported variable and ``DEPLOYMENT.md`` for the
production runbook.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from config import env

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ``manage.py test`` / pytest: keep the relaxed development posture (a real
# SECRET_KEY is not required, HTTPS redirects are not applied) so the suite runs
# under either environment without a live secret. Production security is proven
# separately by ``check --deploy`` under a production environment.
_RUNNING_TESTS = "test" in sys.argv[:3] or "PYTEST_CURRENT_TEST" in os.environ

# --- core -------------------------------------------------------------

DEBUG = env.get_bool("DJANGO_DEBUG", default=env.get_bool("DEBUG", default=False))

# Everything gated on this is real-production-only: skipped in DEBUG and skipped
# while the test suite runs.
IS_PRODUCTION = not DEBUG and not _RUNNING_TESTS

_INSECURE_DEV_SECRET = "django-insecure-local-development-only-change-me"
SECRET_KEY = env.get_str("DJANGO_SECRET_KEY") or env.get_str("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or _RUNNING_TESTS:
        SECRET_KEY = _INSECURE_DEV_SECRET
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is not true. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\". "
            "For local development set DJANGO_DEBUG=True (see .env.example)."
        )
if IS_PRODUCTION and SECRET_KEY == _INSECURE_DEV_SECRET:
    raise ImproperlyConfigured(
        "Refusing to start with the insecure development SECRET_KEY while "
        "DJANGO_DEBUG is false. Set DJANGO_SECRET_KEY to a strong random value."
    )

ALLOWED_HOSTS = env.get_list(
    "DJANGO_ALLOWED_HOSTS",
    default=env.get_list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"]),
)
# Full origins including scheme, e.g. https://hanai.example.org
CSRF_TRUSTED_ORIGINS = env.get_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=env.get_list("CSRF_TRUSTED_ORIGINS", default=[]),
)

# --- applications ---------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.ai",
    "apps.physics",
    "apps.lessons",
    "apps.teachers",
    "apps.students",
    "apps.assessments",
    "apps.provenance",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves collected static files straight from the app server in
    # production; it is a no-op behind ``runserver`` in DEBUG.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- database -----------------------------------------------------
#
# DATABASE_URL wins when set (production PostgreSQL). Otherwise SQLite, so a
# fresh clone and the test suite need no configuration.

_DATABASE_URL = env.get_str("DATABASE_URL")
_DB_CONN_MAX_AGE = env.get_int("DJANGO_DB_CONN_MAX_AGE", default=600 if not DEBUG else 0)

if _DATABASE_URL:
    DATABASES = {
        "default": env.parse_database_url(
            _DATABASE_URL, base_dir=BASE_DIR, conn_max_age=_DB_CONN_MAX_AGE
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- passwords / auth --------------------------------------------
#
# The teacher workspace gates on ``is_staff`` (Django's session auth), and there
# is no separate student login yet. Production deployments should create staff
# accounts with ``createsuperuser`` / the admin -- see DEPLOYMENT.md. Password
# validation below applies to every real account.

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n / time -------------------------------------------------
#
# The analytics and evidence layers rely on timezone-aware datetimes. Do not
# turn USE_TZ off.

LANGUAGE_CODE = "en-us"
TIME_ZONE = env.get_str("DJANGO_TIME_ZONE", "UTC") or "UTC"
USE_I18N = True
USE_TZ = True

# --- static / media -------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Hashed + compressed static in production once ``collectstatic`` has run
# (the Dockerfile / release step sets DJANGO_MANIFEST_STATIC=True). Kept off by
# default so a fresh clone and the test suite need no manifest.
if env.get_bool("DJANGO_MANIFEST_STATIC", default=False):
    _STATICFILES_BACKEND = "whitenoise.storage.CompressedManifestStaticFilesStorage"
else:
    _STATICFILES_BACKEND = "whitenoise.storage.CompressedStaticFilesStorage"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _STATICFILES_BACKEND},
}
# A missing entry in the manifest degrades to the plain path instead of raising.
WHITENOISE_MANIFEST_STRICT = False
# Outside real production, serve static straight from the source dirs via the
# staticfiles finders -- no `collectstatic` needed for `runserver` or the test
# suite.
WHITENOISE_USE_FINDERS = not IS_PRODUCTION
if not IS_PRODUCTION:
    # Ensure STATIC_ROOT exists so WhiteNoise does not warn about it before the
    # first `collectstatic`. Empty and gitignored; production collects into it.
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)

# No user-uploaded media exists in HANAI today (no FileField / ImageField
# anywhere). These are defined only so a future feature has a home; nothing is
# served from MEDIA_ROOT in production.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- security (production only) --------------------------------
#
# Applied only when DJANGO_DEBUG is false and the suite is not running, so local
# development and tests are never redirected to HTTPS or given secure-only
# cookies. ``check --deploy`` under a production environment must be clean.

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True

if IS_PRODUCTION:
    # HTTPS is assumed in production. A platform that terminates TLS and does its
    # own redirect can set DJANGO_SECURE_SSL=False (then check --deploy will warn
    # about W004/W008/W012/W016 -- an explicit, documented operator choice).
    _HTTPS = env.get_bool("DJANGO_SECURE_SSL", default=True)
    if _HTTPS:
        SECURE_SSL_REDIRECT = env.get_bool("DJANGO_SSL_REDIRECT", default=True)
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        # Trust the proxy's X-Forwarded-Proto (Render / Railway / Fly / Heroku).
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        SECURE_HSTS_SECONDS = env.get_int("DJANGO_HSTS_SECONDS", default=31536000)
        SECURE_HSTS_INCLUDE_SUBDOMAINS = env.get_bool(
            "DJANGO_HSTS_INCLUDE_SUBDOMAINS", default=True
        )
        SECURE_HSTS_PRELOAD = env.get_bool("DJANGO_HSTS_PRELOAD", default=True)

# --- logging --------------------------------------------------
#
# Log to stdout/stderr (12-factor); the platform captures it. No file handlers,
# no request headers / cookies / bodies -- Django's own loggers never emit the
# SECRET_KEY, database password, or Authorization headers, and nothing here adds
# them. AI/tutor error paths already use ``logger.exception`` with sanitised
# messages (see apps/ai, apps/students).

LOG_LEVEL = env.get_str("DJANGO_LOG_LEVEL", "INFO").upper() or "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Surface 5xx tracebacks on the console even at higher root levels.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

# --- AI providers --------------------------------------------
#
# Default "fake" so local development and tests never call a remote API.
# "openai" is implemented; "ollama" is reserved. All values come from the
# environment -- never commit a real key.

AI_PROVIDER = env.get_str("AI_PROVIDER", "fake").lower() or "fake"
AI_MODEL = env.get_str("AI_MODEL")
OPENAI_API_KEY = env.get_str("OPENAI_API_KEY")
OPENAI_MODEL = env.get_str("OPENAI_MODEL") or "gpt-4o-mini"
OPENAI_TIMEOUT = env.get_int("OPENAI_TIMEOUT", default=60)
if OPENAI_TIMEOUT <= 0:
    OPENAI_TIMEOUT = 60
OLLAMA_BASE_URL = env.get_str("OLLAMA_BASE_URL") or "http://localhost:11434"
OLLAMA_MODEL = env.get_str("OLLAMA_MODEL") or "llama3.1"
