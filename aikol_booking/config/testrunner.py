"""The project's test runner.

It exists for one reason: the rate limiter keeps its counters in the cache, and
the cache is not part of the database, so Django's per-test transaction rollback
does not clear it. Counters leak from one test into the next, and a test that
registers an account then fails because four earlier tests already used up the
hourly limit.

Clearing the cache before every test is done here rather than in each test's
`setUp`, so a test written next year is isolated without its author having to
know the limiter exists. A test that is *about* the limiter still works: it
fills its own bucket inside its own method.

Two details this got wrong on the first attempt, both worth stating because they
are not obvious from the outside:

  - `_pre_setup` is a **classmethod** in this version of Django, so the patch
    has to be re-wrapped in `classmethod` or it is called with no arguments.
  - `TransactionTestCase` overrides it, and `TestCase` inherits from there. So
    patching `SimpleTestCase` alone silently misses every database test — which
    is nearly all of them.
"""

from __future__ import annotations

from django.core.cache import caches
from django.test.runner import DiscoverRunner
from django.test.testcases import SimpleTestCase, TransactionTestCase

_PATCHED = "_aikol_clears_cache"


def _clear_caches() -> None:
    for alias in caches:
        caches[alias].clear()


def _wrap(cls) -> None:
    if getattr(cls.__dict__.get("_pre_setup"), _PATCHED, False):
        return
    original = cls.__dict__["_pre_setup"].__func__

    def _pre_setup(inner_cls):
        _clear_caches()
        original(inner_cls)

    setattr(_pre_setup, _PATCHED, True)
    cls._pre_setup = classmethod(_pre_setup)


class AikolTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        for cls in (SimpleTestCase, TransactionTestCase):
            _wrap(cls)
