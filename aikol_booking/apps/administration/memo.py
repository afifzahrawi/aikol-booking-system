"""A small in-process memory for what every page reads and rarely changes.

Every page drew the header from SiteContent, and every office page counted
the badges on the rail and checked the email settings: six to eight database
round trips before the page's own work. On the live site each round trip goes
to Supabase, so they were most of the pause after a click.

These values are kept in this process for a few seconds and forgotten the
moment a relevant row is saved or deleted here (see `apps.AdministrationConfig`).
Only one web instance serves the site (`--max 1`). A change made by the
maintenance service, such as a nightly status change, reaches the web
instance when its entries expire.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def remembered(key: str, seconds: float, compute: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = compute()
    with _lock:
        _store[key] = (now + seconds, value)
    return value


def forget(*_args, **_kwargs) -> None:
    """Drop everything. Shaped as a signal receiver so it can be connected directly."""
    with _lock:
        _store.clear()
