"""Settings shared by every environment.

Anything environment-specific — the database, DEBUG, the email backend, secrets —
belongs in development.py or production.py, never here. See
docs/technical/architecture.md.
"""

import os
from pathlib import Path

# aikol_booking/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Overridden in both environments: development supplies a fixed development key,
# production refuses to start without one from the environment.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Order matters only for template and static resolution, not for models.
    "apps.accounts",
    "apps.resources",
    "apps.bookings",
    "apps.notifications",
    "apps.audit",
    "apps.administration",
    "apps.reporting",
    "apps.importexport",
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
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.administration.context_processors.site_content",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# The custom user model. This is set here, before the first migration, because
# it cannot be changed afterwards without recreating the database.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# Malaysia. Times are stored as UTC and rendered in this zone; every booking
# timestamp in this system is a local wall-clock time to the people using it.
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Asia/Kuala_Lumpur"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Uploads. Images only, sniffed rather than trusted, renamed on save — see
# apps/resources/validators.py and docs/technical/security.md.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PERMITTED_IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")

# Self-registration is open to the public, but an IIUM address is what proves an
# IIUM affiliation. A person with neither may still register; they simply carry
# no matriculation or staff number. See decision 1 and the follow-up decisions.
IIUM_EMAIL_DOMAINS = ("iium.edu.my", "live.iium.edu.my")

# How long a verification or password-reset link stays usable.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3  # three days

DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "AIKOL Booking <booking-aikol@iium.edu.my>"
)
