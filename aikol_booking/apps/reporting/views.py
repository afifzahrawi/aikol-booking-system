"""The Insights screen."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from . import services

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def approver_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Sign in first.")
        if not request.user.is_approver:
            raise PermissionDenied("Only an approver or administrator may read reports.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


@approver_required
def reports(request):
    today = timezone.localdate()
    terms = services.started_terms(today)
    period = services.resolve_period(request.GET, today, terms)
    venues = services.active_venues()
    vehicles = services.active_vehicles()

    bookings = services.period_bookings(period.start, period.end)
    heat = services.demand_heatmap(bookings)
    for row in heat["rows"]:
        row["name"] = WEEKDAY_NAMES[row["weekday"]]
    if heat["busiest"]:
        heat["busiest"]["name"] = WEEKDAY_NAMES[heat["busiest"]["weekday"]]

    tab = request.GET.get("tab")
    # The tab links keep the period; the tabs switch in place when script runs.
    keep = request.GET.copy()
    keep.pop("tab", None)
    return render(
        request,
        "reporting/reports.html",
        {
            "period": period,
            "periods": services.PERIODS,
            "terms": terms,
            "query": keep.urlencode(),
            "tab": tab if tab in {"venues", "vehicles", "office", "people"} else "venues",
            "attention": services.attention(vehicles, today),
            "kpis": services.kpis(period, venues),
            "venue_use": services.venue_use(period, venues),
            "heat": heat,
            "monthly": services.monthly_volume(period, today),
            "vehicle_use": services.vehicle_use(period, vehicles),
            "office": services.office_work(period),
            "groups": services.by_affiliation(bookings),
            "requesters": services.frequent_requesters(bookings),
        },
    )
