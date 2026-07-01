"""
Django settings for the Nemo Water Risk platform.

Reads configuration from environment (.env). Uses PostGIS via
django.contrib.gis. Keep secrets out of source control.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",  # PostGIS / spatial fields
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [BASE_DIR / "reports" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database (PostGIS) -----------------------------------------------------
# Parses DATABASE_URL of the form:
#   postgis://USER:PASSWORD@HOST:PORT/NAME
def _parse_database_url(url: str) -> dict:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": parsed.path.lstrip("/") or "nemo_waterrisk",
        "USER": parsed.username or "nemo",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "localhost",
        "PORT": str(parsed.port or 5432),
    }


DATABASES = {
    "default": _parse_database_url(
        os.getenv("DATABASE_URL", "postgis://nemo:nemo@localhost:5432/nemo_waterrisk")
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Celery -----------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_TRACK_STARTED = True


# --- Nemo agent configuration ----------------------------------------------
NEMO = {
    "LLM_MODEL": os.getenv("NEMO_LLM_MODEL", ""),  # required at call time
    "LLM_TIMEOUT_MS": int(os.getenv("NEMO_LLM_TIMEOUT_MS", "45000")),
    "LLM_MAX_TOKENS": int(os.getenv("NEMO_LLM_MAX_TOKENS", "2000")),
    "LLM_MAX_RESPONSE_CHARS": int(os.getenv("NEMO_LLM_MAX_RESPONSE_CHARS", "20000")),
    # Absolute path; all agent file writes are jailed inside this root.
    "WORKSPACE_ROOT": str((BASE_DIR / os.getenv("NEMO_WORKSPACE_ROOT", "workspace")).resolve()),
    "MAX_CONCURRENCY": int(os.getenv("NEMO_MAX_CONCURRENCY", "2")),
    "RISK_CHANGE_THRESHOLD": float(os.getenv("NEMO_RISK_CHANGE_THRESHOLD", "5")),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json_like": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json_like"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
