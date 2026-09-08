#!/usr/bin/env python
"""Django's command-line utility.

Defaults to development settings so that `python manage.py runserver` works with
no environment set up. Production passes DJANGO_SETTINGS_MODULE explicitly.
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django is not importable. Is the virtual environment active?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
