"""The one cipher for secrets the application stores on behalf of a person.

It lives in `config/` for the same reason `config/forms.py` does: `accounts`
and `notifications` both need it, and neither should import the other for
plumbing. The key comes from the environment and is never in the repository.
"""

from __future__ import annotations

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def credential_cipher() -> Fernet:
    key = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured(
            "DJANGO_CREDENTIAL_ENCRYPTION_KEY is required for stored credentials."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "DJANGO_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc
