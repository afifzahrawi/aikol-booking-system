"""Run the complete user-action regression matrix against a disposable test DB.

This never connects to production: it forces development settings, which use
SQLite, and Django's test runner creates and destroys a separate test database.
The route inventory is deliberately explicit so adding a user-facing action
requires acknowledging it here. Tests cover successful and refused operations;
real SMTP delivery and browser-only behaviour still require UAT.

Usage: .venv/Scripts/python.exe tools/test_action_matrix.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "aikol_booking"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.development"
os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(APP))

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.urls import get_resolver  # noqa: E402
from django.urls.resolvers import URLPattern, URLResolver  # noqa: E402


ACTION_ROUTES = {
    "accounts": {
        "dashboard", "login", "logout", "profile", "register", "register_done",
        "verify", "password_reset", "password_reset_done", "password_reset_confirm",
        "password_reset_complete", "mfa_enrol", "mfa_verify",
    },
    "resources": {
        "venues", "vehicles", "detail", "manage_venues", "venue_new", "venue_edit",
        "manage_vehicles", "vehicle_new", "vehicle_edit", "delete", "images",
        "image_delete", "manage_facilities", "facility_new", "facility_edit",
        "facility_reorder", "facility_delete",
    },
    "bookings": {
        "mine", "detail", "cancel", "series_cancel", "availability", "create",
        "slot_check", "series_create", "approvals", "decide", "decide_series",
        "manage", "admin_start", "admin_create", "admin_series_create", "user_search",
        "vehicle_management", "academic_terms", "academic_term_new",
        "academic_term_edit", "keys", "key_issue", "key_return",
    },
    "administration": {
        "dashboard", "users", "user_edit", "user_mfa_reset", "settings", "site_content",
        "announcement_new", "announcement_edit", "audit", "retention",
    },
    "importexport": {
        "data_management", "confirm", "template", "export_users", "export_venues",
        "export_vehicles", "export_facilities", "export_bookings",
    },
    "reporting": {"reports"},
}


def route_names(patterns, namespace="") -> set[str]:
    found = set()
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            if pattern.namespace == "admin":
                continue  # Django's own administration has its own test suite.
            child_namespace = f"{namespace}{pattern.namespace}:" if pattern.namespace else namespace
            found.update(route_names(pattern.url_patterns, child_namespace))
        elif isinstance(pattern, URLPattern) and pattern.name and pattern.name != "maintenance-task":
            found.add(f"{namespace}{pattern.name}")
    return found


def main() -> int:
    if settings.DEBUG is not True or settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
        print("REFUSED: this script only runs with the local SQLite development settings.")
        return 2

    expected = {f"{app}:{name}" for app, names in ACTION_ROUTES.items() for name in names}
    actual = route_names(get_resolver().url_patterns)
    if actual != expected:
        print("Action inventory is out of date:")
        for name in sorted(actual - expected):
            print(f"  NEW route without matrix entry: {name}")
        for name in sorted(expected - actual):
            print(f"  Removed route still in matrix: {name}")
        return 2

    print("Action inventory (user-facing named routes):")
    for app, names in ACTION_ROUTES.items():
        print(f"  {app}: {len(names)} routes")
    print(f"  Total: {len(expected)} routes")
    print("Running all application and infrastructure tests in a disposable database...", flush=True)
    result = subprocess.run(
        [sys.executable, str(APP / "manage.py"), "test", "apps", "config", "--noinput"],
        cwd=ROOT,
        env=os.environ.copy(),
        check=False,
    )
    print("PASS: action regression suite" if result.returncode == 0 else "FAIL: action regression suite")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
