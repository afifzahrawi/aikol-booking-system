"""Development settings: SQLite, DEBUG on, email printed to the console.

SQLite is deliberate and documented — it needs no setup. It is NOT production:
the exclusion constraint that guarantees no overlapping bookings requires
PostgreSQL, so `manage.py check` warns when this file is in use.
"""

from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True
SECRET_KEY = "django-insecure-development-only-do-not-use-in-production"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Mail is written to the console. The outbox table is still used — queue_email()
# writes a row and `manage.py send_queued_email` drains it — so the development
# path exercises the same code as production.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
