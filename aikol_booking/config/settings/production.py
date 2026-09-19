"""Production settings: PostgreSQL, DEBUG off, HTTPS enforced.

Every secret comes from the environment. Nothing here may fall back to a usable
default — a missing variable must stop the application starting, not silently
run it with a known key.
"""

import os

import dj_database_url
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
CREDENTIAL_ENCRYPTION_KEY = required("DJANGO_CREDENTIAL_ENCRYPTION_KEY")
ALLOWED_HOSTS = [h.strip() for h in required("DJANGO_ALLOWED_HOSTS").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

# PostgreSQL is required, not preferred: the overlap exclusion constraint that
# makes double booking impossible at the database level has no SQLite equivalent.
DATABASES = {
    "default": dj_database_url.parse(
        required("DATABASE_URL"),
        conn_max_age=60,
        conn_health_checks=True,
        ssl_require=True,
    )
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

# WhiteNoise serves immutable, hashed static assets directly from the web
# container. User uploads never live on its ephemeral filesystem: they go to
# Cloudflare R2 through its S3-compatible API.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "config.storage.CappedR2Storage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
AWS_ACCESS_KEY_ID = required("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = required("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = required("R2_BUCKET_NAME")
AWS_S3_ENDPOINT_URL = required("R2_ENDPOINT_URL")
AWS_S3_REGION_NAME = "auto"
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 3600
AWS_S3_FILE_OVERWRITE = False
# Keep uploaded images private. Django generates a one-hour signed R2 URL when
# rendering an image; unlike a public development URL, this does not expose the
# entire bucket or require another public hostname.
AWS_S3_CUSTOM_DOMAIN = None
MEDIA_URL = f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{AWS_STORAGE_BUCKET_NAME}/"

# R2 includes 10 GB-month of Standard storage, but its budget alerts do not stop
# usage.  Media and backups therefore receive separate ceilings with substantial
# headroom for delayed metrics and concurrent requests.
R2_MEDIA_SOFT_LIMIT_BYTES = int(
    os.environ.get("R2_MEDIA_SOFT_LIMIT_BYTES", 2 * 1024 * 1024 * 1024)
)
R2_BACKUP_SOFT_LIMIT_BYTES = int(
    os.environ.get("R2_BACKUP_SOFT_LIMIT_BYTES", 7 * 1024 * 1024 * 1024)
)
R2_BACKUP_MAX_OBJECTS = int(os.environ.get("R2_BACKUP_MAX_OBJECTS", 14))

# The outbox worker builds its SMTP connection from the encrypted profile on
# the administrator System screen. Requests never talk to SMTP directly.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# The full database reset is disabled in production by default (see the data
# protection rules in CLAUDE.md, section 8).
ALLOW_FULL_RESET = os.environ.get("DJANGO_ALLOW_FULL_RESET", "0") == "1"

# Only the private Cloud Run maintenance service sets this. The public service
# returns 404 for maintenance URLs even if somebody discovers their names.
MAINTENANCE_SERVICE = os.environ.get("DJANGO_MAINTENANCE_SERVICE", "0") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
