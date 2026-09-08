"""The reports screen."""

from __future__ import annotations

import datetime as dt

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
    try:
        days = max(7, min(365, int(request.GET.get("days", 90))))
    except (TypeError, ValueError):
        days = 90
    start = today - dt.timedelta(days=days)

    bookings = services.period_bookings(start, today)
    heat = services.demand_heatmap(bookings)
    for row in heat["rows"]:
        row["name"] = WEEKDAY_NAMES[row["weekday"]]
    if heat["busiest"]:
        heat["busiest"]["name"] = WEEKDAY_NAMES[heat["busiest"]["weekday"]]

    return render(
        request,
        "reporting/reports.html",
        {
            "days": days,
            "start": start,
            "today": today,
            "headline": services.headline(bookings),
            "heat": heat,
            "utilisation": services.utilisation(bookings, days=days),
            "monthly": services.monthly_volume(),
            "requesters": services.frequent_requesters(bookings),
            "keys": services.key_summary(),
        },
    )
