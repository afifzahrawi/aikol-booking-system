"""Production settings: PostgreSQL, DEBUG off, HTTPS enforced.

Every secret comes from the environment. Nothing here may fall back to a usable
default — a missing variable must stop the application starting, not silently
run it with a known key.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(
            f"{name} is not set. Production refuses to start without it."
        )
    return value


DEBUG = False
SECRET_KEY = required("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [h.strip() for h in required("DJANGO_ALLOWED_HOSTS").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS]

# PostgreSQL is required, not preferred: the overlap exclusion constraint that
# makes double booking impossible at the database level has no SQLite equivalent.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required("DJANGO_DB_NAME"),
        "USER": required("DJANGO_DB_USER"),
        "PASSWORD": required("DJANGO_DB_PASSWORD"),
        "HOST": os.environ.get("DJANGO_DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DJANGO_DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# The DATABASE cache, not local memory. Gunicorn runs several worker
# processes; a per-process rate-limit counter would give an attacker one bucket
# per worker, quietly multiplying every limit by the worker count. Create the
# table once with `manage.py createcachetable`.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "aikol_cache",
    }
}

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # the token is read by the form, not by script
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# The outbox holds the message; cron delivers it. Nothing in a request path
# talks to SMTP, so a slow mail server cannot fail a booking.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("DJANGO_EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("DJANGO_EMAIL_USE_TLS", "1") == "1"

MEDIA_ROOT = os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media"))  # noqa: F405

# The full database reset is disabled in production by default (see the data
# protection rules in CLAUDE.md, section 8).
ALLOW_FULL_RESET = os.environ.get("DJANGO_ALLOW_FULL_RESET", "0") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
