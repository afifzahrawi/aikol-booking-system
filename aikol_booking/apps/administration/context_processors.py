"""Context every template needs, so no view has to remember to supply it."""

from __future__ import annotations

from django.urls import reverse

from .models import SiteContent


def site_content(request):
    """Header and footer wording, available to every template."""
    # Django's built-in authentication views already use the key ``site`` for
    # RequestSite. A distinct key keeps editable content from being replaced on
    # the sign-in and password-reset screens.
    return {"site_content": SiteContent.load()}


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
        shell_nav = "dashboard"
    elif path.startswith("/bookings/"):
        shell_nav = "mine"
    elif path.startswith("/rooms/"):
        shell_nav = "venues"
    elif path.startswith("/cars/"):
        shell_nav = "vehicles"
    else:
        shell_nav = ""

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
            "back_fallback_url": reverse("accounts:dashboard"),
        }

    from apps.bookings.models import Booking, BookingStatus

    admin_paths = ("/manage/", "/approvals/")
    if path == "/manage/":
        shell_nav = "dashboard"
    elif path.startswith(("/manage/bookings/", "/approvals/")):
        shell_nav = "bookings" if user.is_administrator else "approvals"
    elif path.startswith("/manage/keys/"):
        shell_nav = "keys"
    elif path.startswith(("/manage/rooms/", "/manage/cars/", "/manage/facilities/", "/manage/resource/")):
        shell_nav = "resources"
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
    }
    return {
        "admin_area": is_admin_area,
        "pending_count": Booking.objects.filter(status=BookingStatus.PENDING).count(),
        "shell_nav": shell_nav,
        "show_back_navigation": view_name not in (admin_roots if is_admin_area else requester_roots),
        "back_fallback_url": reverse(
            "administration:dashboard" if is_admin_area else "accounts:dashboard"
        ),
    }
