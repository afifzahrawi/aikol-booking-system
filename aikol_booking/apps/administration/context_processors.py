"""Context every template needs, so no view has to remember to supply it."""

from __future__ import annotations

from .models import SiteContent


def site_content(request):
    """Header and footer wording, available to every template."""
    return {"site": SiteContent.load()}


def chrome(request):
    """Which navigation bar to draw, and the badge on the approvals link.

    `admin_area` is decided from the path rather than passed by each view: a
    view that forgot to set it would silently render the wrong navigation, and
    that is exactly the kind of inconsistency nobody notices until a user does.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_approver:
        return {"admin_area": False, "pending_count": 0}

    from apps.bookings.models import Booking, BookingStatus

    admin_paths = ("/manage/", "/approvals/")
    return {
        "admin_area": request.path.startswith(admin_paths),
        "pending_count": Booking.objects.filter(status=BookingStatus.PENDING).count(),
    }
