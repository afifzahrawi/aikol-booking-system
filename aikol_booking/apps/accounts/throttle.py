"""Rate limiting for the public authentication endpoints.

A public registration form on a public domain will be probed. Without a limit,
registration, sign-in and password reset are all free credential-stuffing and
address-enumeration surfaces.

Implemented on Django's cache framework rather than a new dependency. In
production the cache backend is the **database**, not local memory: Gunicorn
runs several worker processes, and a per-process counter would give an attacker
one bucket per worker — a limit of five attempts silently becomes five times the
number of workers. That is the kind of mistake that looks like it works.

Two buckets per endpoint, and both matter:

  - **per IP**, which catches one machine trying many accounts;
  - **per identifier** (the email being tried), which catches a distributed
    attempt on one account.

Exceeding either refuses the request. The refusal never says which bucket
tripped, and never says whether the account exists.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from django.core.cache import cache


@dataclass(frozen=True)
class Limit:
    """`attempts` tries allowed per `window` seconds."""

    attempts: int
    window: int


#: Deliberately generous for a human and useless for a script. Registration is
#: tighter than sign-in because a person registers once and mistypes a password
#: often.
LIMITS = {
    "register": Limit(attempts=5, window=60 * 60),
    "login": Limit(attempts=10, window=15 * 60),
    "password_reset": Limit(attempts=5, window=60 * 60),
    "verify": Limit(attempts=20, window=60 * 60),
}


def client_ip(request) -> str:
    """The client address.

    `X-Forwarded-For` is trusted only because Nginx sits in front and overwrites
    it. If this application is ever exposed directly, the header is
    attacker-controlled and this must change — hence the comment rather than a
    silent assumption.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _key(scope: str, bucket: str, value: str) -> str:
    # Hashed so an email address is not sitting in the cache as plain text, and
    # so an over-long value cannot break the key length limit.
    digest = hashlib.sha256(value.lower().encode()).hexdigest()[:32]
    return f"throttle:{scope}:{bucket}:{digest}"


def _count(key: str, window: int) -> int:
    """Increment and return the count for this key.

    `cache.add` then `cache.incr` rather than get-modify-set: the add is atomic
    on every backend, so two simultaneous requests cannot both read zero.
    """
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # The entry expired between the add and the incr. Start again.
        cache.set(key, 1, window)
        return 1


def is_throttled(request, scope: str, identifier: str = "") -> bool:
    """True when this request should be refused. Counts the attempt either way."""
    limit = LIMITS[scope]
    over = False
    if _count(_key(scope, "ip", client_ip(request)), limit.window) > limit.attempts:
        over = True
    if identifier and _count(_key(scope, "id", identifier), limit.window) > limit.attempts:
        over = True
    return over


def reset(scope: str, identifier: str) -> None:
    """Clear the identifier bucket after a genuine success, so somebody who
    finally remembers their password is not locked out by their own typos."""
    cache.delete(_key(scope, "id", identifier))
