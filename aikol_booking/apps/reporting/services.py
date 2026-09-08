"""Aggregations for the reports screen.

Everything here runs in the query where it can. The one exception is the demand
heatmap, which spreads each booking across the hours it occupies — that is not
expressible as a GROUP BY without either denormalising hours into rows or
misattributing a 09:00–12:00 seminar to a single bucket.
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.keys import outstanding_keys
from apps.bookings.models import BLOCKING_STATUSES, Booking, BookingStatus
from apps.resources.models import Resource, ResourceStatus, ResourceType

#: The bookable window, and therefore the heatmap's rows.
WINDOW_START, WINDOW_END = 8, 22

#: Statuses that represent a booking that actually happened or will.
HONOURED = (BookingStatus.APPROVED, BookingStatus.COMPLETED)


def period_bookings(start: dt.date, end: dt.date) -> QuerySet[Booking]:
    begin = timezone.make_aware(dt.datetime.combine(start, dt.time.min))
    finish = timezone.make_aware(dt.datetime.combine(end, dt.time.max))
    return Booking.objects.filter(start_at__gte=begin, start_at__lte=finish)


def headline(bookings: QuerySet[Booking]) -> dict:
    counts = dict(
        bookings.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )
    approved = counts.get(BookingStatus.APPROVED, 0) + counts.get(BookingStatus.COMPLETED, 0)
    rejected = counts.get(BookingStatus.REJECTED, 0)
    decided = approved + rejected
    room_minutes = 0
    trip_days = 0
    for start, end, kind in bookings.filter(status__in=HONOURED).values_list(
        "start_at", "end_at", "resource__resource_type"
    ):
        if kind == ResourceType.VENUE:
            room_minutes += (end - start).total_seconds() / 60
        else:
            trip_days += max(1, (timezone.localtime(end).date()
                                 - timezone.localtime(start).date()).days + 1)
    return {
        "total": bookings.count(),
        "approved": approved,
        "rejected": rejected,
        "cancelled": counts.get(BookingStatus.CANCELLED, 0),
        "pending": counts.get(BookingStatus.PENDING, 0),
        "approval_rate": round(approved / decided * 100) if decided else None,
        "room_hours": round(room_minutes / 60),
        "trip_days": trip_days,
    }


def demand_heatmap(bookings: QuerySet[Booking]) -> dict:
    """Room-hours booked, by weekday and hour of the bookable window.

    Each booking is spread across the hours it actually occupies, with part
    hours counted as fractions — so a 09:00–12:00 seminar adds an hour to each
    of three cells rather than three hours to one, and a 30-minute booking does
    not look the same as a 3-hour one.

    Vehicles are excluded: a trip that runs overnight has no meaningful hour of
    day, and averaging one into this grid would be noise dressed as data.
    """
    hours = list(range(WINDOW_START, WINDOW_END))
    cells = [[0.0] * len(hours) for _ in range(7)]

    rows = bookings.filter(
        status__in=HONOURED, resource__resource_type=ResourceType.VENUE
    ).values_list("start_at", "end_at")

    for start_utc, end_utc in rows:
        start = timezone.localtime(start_utc)
        end = timezone.localtime(end_utc)
        weekday = start.weekday()
        from_hour = start.hour + start.minute / 60
        to_hour = from_hour + (end - start).total_seconds() / 3600
        for index, hour in enumerate(hours):
            overlap = min(to_hour, hour + 1) - max(from_hour, hour)
            if overlap > 0:
                cells[weekday][index] += overlap

    peak = max((max(row) for row in cells), default=0)
    busiest = None
    if peak > 0:
        for day, row in enumerate(cells):
            for index, value in enumerate(row):
                if value == peak:
                    busiest = {"weekday": day, "hour": hours[index], "value": round(peak, 1)}
                    break
            if busiest:
                break

    def level(value: float) -> int:
        # An empty hour keeps level 0 rather than the palest step: "nobody
        # booked this" and "one person booked this" differ in kind, and a ramp
        # that blends them hides the dead parts of the day the chart exists to
        # find.
        if value <= 0:
            return 0
        return min(5, max(1, int(-(-value / peak * 5 // 1))))

    return {
        "hours": hours,
        "rows": [
            {
                "weekday": day,
                "cells": [
                    {"hour": hours[i], "value": round(v, 1), "level": level(v)}
                    for i, v in enumerate(row)
                ],
            }
            for day, row in enumerate(cells)
        ],
        "peak": round(peak, 1),
        "busiest": busiest,
        "total": round(sum(sum(row) for row in cells), 1),
    }


def utilisation(bookings: QuerySet[Booking], *, days: int) -> list[dict]:
    """Share of the bookable window each resource actually held."""
    window_hours = (WINDOW_END - WINDOW_START) * days
    booked: dict[int, float] = {}
    for resource_id, start, end in bookings.filter(status__in=HONOURED).values_list(
        "resource_id", "start_at", "end_at"
    ):
        booked[resource_id] = booked.get(resource_id, 0) + (end - start).total_seconds() / 3600

    out = []
    for resource in Resource.objects.filter(status=ResourceStatus.ACTIVE):
        hours = booked.get(resource.pk, 0)
        out.append(
            {
                "resource": resource,
                "hours": round(hours, 1),
                "percent": min(100, round(hours / window_hours * 100)) if window_hours else 0,
            }
        )
    return sorted(out, key=lambda row: row["percent"], reverse=True)


def monthly_volume(months: int = 12) -> list[dict]:
    today = timezone.localdate()
    out = []
    for offset in range(months - 1, -1, -1):
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        start = dt.date(year, month, 1)
        end = dt.date(year + (month == 12), (month % 12) + 1, 1)
        count = Booking.objects.filter(
            created_at__gte=timezone.make_aware(dt.datetime.combine(start, dt.time.min)),
            created_at__lt=timezone.make_aware(dt.datetime.combine(end, dt.time.min)),
        ).count()
        out.append({"label": start.strftime("%b"), "year": year, "count": count})
    peak = max((row["count"] for row in out), default=0) or 1
    for row in out:
        row["percent"] = round(row["count"] / peak * 100)
    return out


def frequent_requesters(bookings: QuerySet[Booking], limit: int = 10) -> list[dict]:
    """Names and counts only.

    No matriculation number and no telephone number: this is a utilisation
    report, and its purpose does not require them.
    """
    rows = (
        bookings.values("user__full_name", "user__affiliation")
        .annotate(n=Count("id"))
        .order_by("-n")[:limit]
    )
    return [
        {
            "name": row["user__full_name"],
            "affiliation": row["user__affiliation"],
            "count": row["n"],
        }
        for row in rows
    ]


def key_summary() -> dict:
    now = timezone.now()
    out = outstanding_keys()
    return {
        "out": out.count(),
        "overdue": out.filter(booking__end_at__lt=now).count(),
        "uncollected": Booking.objects.filter(
            status=BookingStatus.COMPLETED, key_handover__isnull=True
        ).count(),
    }
