"""Development settings on PostgreSQL, for the test run that SQLite cannot give.

The exclusion constraints in bookings/0002 and the row-locking concurrency test
only exist on PostgreSQL. Everything else is development.py. Point DATABASE_URL
at any disposable PostgreSQL 15+ instance:

    DJANGO_SETTINGS_MODULE=config.settings.postgres \
    DATABASE_URL=postgresql://postgres@localhost:5499/postgres \
    python manage.py test
"""

import os

import dj_database_url

from .development import *  # noqa: F401,F403

DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}
