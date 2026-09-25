"""Context every template needs, so no view has to remember to supply it."""

from __future__ import annotations

import re

from django.urls import reverse

from .models import SiteContent

#: /resource/19/, /resource/19/availability/, /resource/19/book/ and the weekly
#: form all hang off one resource, but the path does not say whether it is a
#: room or a car, so the rail highlighted neither. /series/<pk>/ is deliberately
#: not here: that number is a series, not a resource.
RESOURCE_PATH = re.compile(r"^/(?:manage/)?resource/(\d+)/")

#: Where Back goes when there is nowhere to go back to. The section the page
#: belongs to, not the dashboard: somebody editing a room's photographs wants
#: the room list, and being sent to the Overview loses their place.
SECTION_ROOTS = {
    "home": "accounts:dashboard",
    "mine": "bookings:mine",
    "venues": "resources:venues",
    "vehicles": "resources:vehicles",
    "overview": "administration:dashboard",
    "bookings": "bookings:manage",
    "approvals": "bookings:approvals",
    "keys": "bookings:keys",
    "resources": "resources:manage_venues",
    "users": "administration:users",
    "reports": "reporting:reports",
    "system": "administration:settings",
}


def _resource_kind(path: str) -> str:
    """"VENUE", "VEHICLE" or "" for a path that names one resource."""
    match = RESOURCE_PATH.match(path)
    if not match:
        return ""
    from apps.resources.models import Resource

    return (
        Resource.objects.filter(pk=match.group(1))
        .values_list("resource_type", flat=True)
        .first()
        or ""
    )


def _resource_nav(path: str) -> str:
    kind = _resource_kind(path)
    return {"VENUE": "venues", "VEHICLE": "vehicles"}.get(kind, "")


def site_content(request):
    """Header and footer wording, available to every template."""
    # Django's built-in authentication views already use the key ``site`` for
    # RequestSite. A distinct key keeps editable content from being replaced on
    # the sign-in and password-reset screens.
    return {"site_content": SiteContent.load()}


def _section_root(path: str, shell_nav: str, is_admin_area: bool) -> str:
    """The list a page belongs to. A room's photographs belong to the room
    list, and a car's to the car list, which the nav key alone cannot say."""
    if shell_nav == "resources":
        kind = _resource_kind(path)
        if kind == "VEHICLE" or path.startswith("/manage/cars/"):
            return "resources:manage_vehicles"
        if path.startswith("/manage/facilities/"):
            return "resources:manage_facilities"
    default = "administration:dashboard" if is_admin_area else "accounts:dashboard"
    return SECTION_ROOTS.get(shell_nav, default)


def chrome(request):
    """Which navigation bar to draw, and the badge on the approvals link.

    `admin_area` is decided from the path rather than passed by each view: a
    view that forgot to set it would silently render the wrong navigation, and
    that is exactly the kind of inconsistency nobody notices until a user does.
    """
    user = getattr(request, "user", None)
    path = request.path
    if not user or not user.is_authenticated:
        return {
            "admin_area": False,
            "pending_count": 0,
            "shell_nav": "",
            "show_back_navigation": False,
            "back_fallback_url": "/",
        }

    if path == "/":
        shell_nav = "home"
    elif path.startswith("/bookings/"):
        shell_nav = "mine"
    elif path.startswith("/rooms/"):
        shell_nav = "venues"
    elif path.startswith("/cars/"):
        shell_nav = "vehicles"
    else:
        shell_nav = _resource_nav(path)

    requester_roots = {
        "accounts:dashboard",
        "bookings:mine",
        "resources:venues",
        "resources:vehicles",
    }
    view_name = getattr(request.resolver_match, "view_name", "")

    if not user.is_approver:
        return {
            "admin_area": False,
            "pending_count": 0,
            "shell_nav": shell_nav,
            "show_back_navigation": view_name not in requester_roots,
            "back_fallback_url": reverse(
                SECTION_ROOTS.get(shell_nav, "accounts:dashboard")
            ),
        }

    from apps.bookings.models import Booking, BookingStatus

    admin_paths = ("/manage/", "/approvals/")
    if path == "/manage/":
        shell_nav = "overview"
    elif path.startswith(("/manage/bookings/", "/approvals/")):
        shell_nav = "bookings" if user.is_administrator else "approvals"
    elif path.startswith("/manage/keys/"):
        shell_nav = "keys"
    elif path.startswith(("/manage/rooms/", "/manage/cars/", "/manage/facilities/", "/manage/resource/")):
        shell_nav = "resources"
    elif path.startswith("/resource/"):
        # An administrator looking at a room or car from the requester side
        # sees the requester rail; keep the resource kind highlighted there.
        shell_nav = shell_nav or _resource_nav(path)
    elif path.startswith("/manage/users/"):
        shell_nav = "users"
    elif path.startswith("/manage/reports/"):
        shell_nav = "reports"
    elif path.startswith("/manage/"):
        shell_nav = "system"
    is_admin_area = request.path.startswith(admin_paths)
    admin_roots = {
        "administration:dashboard",
        "bookings:manage",
        "bookings:approvals",
        "bookings:keys",
        "resources:manage_venues",
        "resources:manage_vehicles",
        "resources:manage_facilities",
        "administration:users",
        "reporting:reports",
        "administration:settings",
        "administration:site_content",
        "administration:audit",
        # The System tabs are one level: none of them is deeper than another.
        "bookings:academic_terms",
        "importexport:data_management",
        "administration:email_list",
    }
    return {
        "admin_area": is_admin_area,
        "pending_count": Booking.objects.filter(status=BookingStatus.PENDING).count(),
        "shell_nav": shell_nav,
        "show_back_navigation": view_name not in (admin_roots if is_admin_area else requester_roots),
        "back_fallback_url": reverse(_section_root(path, shell_nav, is_admin_area)),
    }
