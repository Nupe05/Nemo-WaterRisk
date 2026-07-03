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
# Heroku dynos are reached via *.herokuapp.com (and your custom domain).
ALLOWED_HOSTS += [".herokuapp.com"]

# CSRF: the public signup form POSTs, so the site's HTTPS origin must be trusted.
CSRF_TRUSTED_ORIGINS = [
    o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
] + ["https://*.herokuapp.com"]

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
    # WhiteNoise serves static files directly from the web dyno (no S3 needed).
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
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email (report delivery) ------------------------------------------------
# Defaults to the console backend: sending a report just prints it to the logs,
# so the flow works with zero setup. To send real email, set
# DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the
# EMAIL_HOST/USER/PASSWORD vars (e.g. Gmail app password, Postmark, SES).
EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Nemo Water Risk <reports@example.com>")

# Geospatial library paths. Left as None (Django auto-detects) locally; on
# Heroku's apt buildpack you can point these at the installed .so files if
# auto-detection fails (see docs/DEPLOY_HEROKU.md).
GDAL_LIBRARY_PATH = os.getenv("GDAL_LIBRARY_PATH") or None
GEOS_LIBRARY_PATH = os.getenv("GEOS_LIBRARY_PATH") or None

# Production security (only when DEBUG is off, i.e. on Heroku).
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Opt-in (default off) so CI / test clients aren't 301-redirected to HTTPS.
    # Turn on in real production: heroku config:set DJANGO_SECURE_SSL_REDIRECT=true
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0


# --- Celery -----------------------------------------------------------------
# Heroku Redis exposes REDIS_URL; fall back to it if the explicit vars are unset.
_redis = os.getenv("REDIS_URL", "redis://localhost:6379")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", f"{_redis}/0" if _redis.count("/") < 4 else _redis)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
# Heroku Redis uses TLS (rediss://) with self-signed certs.
if CELERY_BROKER_URL.startswith("rediss://"):
    import ssl

    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE}
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE}


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
