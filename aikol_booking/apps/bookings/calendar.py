"""The office's booking calendar: a week of days, or one day by room.

Laid out like a desktop calendar (Google Calendar, Teams). Every position is a
percentage of the bookable window, computed here so the template only places
boxes: a booking's top and height within its day column, or its left and width
along a room's row. Bookings that overlap within one day sit side by side in
lanes, as a calendar shows double-booked meetings, so none hides another.
"""

from __future__ import annotations

import calendar as pycal
import datetime as dt
from dataclasses import dataclass, field

from django.db.models import Q
from django.utils import timezone

from apps.administration.models import SystemSetting
from apps.resources.models import Resource, ResourceStatus, ResourceType

from .models import BLOCKING_STATUSES, Booking, BookingStatus

KINDS = {"venue": ResourceType.VENUE, "vehicle": ResourceType.VEHICLE}


@dataclass
class Block:
    booking: Booking
    start_minutes: int
    end_minutes: int
    label: str
    lane: int = 0
    lanes: int = 1
    top: float = 0.0
    height: float = 0.0
    left: float = 0.0
    width: float = 0.0

    @property
    def is_vehicle(self) -> bool:
        return self.booking.resource.resource_type == ResourceType.VEHICLE

    @property
    def is_pending(self) -> bool:
        return self.booking.status == BookingStatus.PENDING


@dataclass
class Day:
    date: dt.date
    is_today: bool
    blocks: list[Block] = field(default_factory=list)


def window() -> tuple[int, int]:
    """The bookable window in minutes since midnight, 08:00 to 22:00 by default."""
    opens = dt.time.fromisoformat(SystemSetting.get("bookable_window_start"))
    closes = dt.time.fromisoformat(SystemSetting.get("bookable_window_end"))
    return opens.hour * 60 + opens.minute, closes.hour * 60 + closes.minute


def monday_of(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def bookings_between(start: dt.date, end: dt.date, *, kinds: set[str], term: str = ""):
    """Live bookings touching [start, end), in the query, with what the cards need."""
    tz = timezone.get_current_timezone()
    since = dt.datetime.combine(start, dt.time.min, tzinfo=tz)
    until = dt.datetime.combine(end, dt.time.min, tzinfo=tz)
    rows = (
        Booking.objects.filter(
            status__in=list(BLOCKING_STATUSES) + [BookingStatus.COMPLETED],
            start_at__lt=until,
            end_at__gt=since,
            resource__resource_type__in=[KINDS[k] for k in kinds],
        )
        .select_related("resource", "user", "series", "key_handover")
        .order_by("start_at")
    )
    if term:
        rows = rows.filter(
            Q(booking_reference__icontains=term)
            | Q(user__full_name__icontains=term)
            | Q(resource__name__icontains=term)
            | Q(purpose__icontains=term)
        )
    return list(rows)


def _clip(booking: Booking, day: dt.date, opens: int, closes: int) -> Block | None:
    """The part of a booking that falls on `day`, inside the bookable window."""
    start = timezone.localtime(booking.start_at)
    end = timezone.localtime(booking.end_at)
    if start.date() > day or end.date() < day:
        return None
    lo = opens if start.date() < day else max(opens, start.hour * 60 + start.minute)
    hi = closes if end.date() > day else min(closes, end.hour * 60 + end.minute)
    if hi <= lo:
        return None
    if start.date() < day and end.date() > day:
        label = "All day"
    elif start.date() < day:
        label = f"Until {end:%H:%M}"
    elif end.date() > day:
        label = f"From {start:%H:%M}"
    else:
        label = f"{start:%H:%M} to {end:%H:%M}"
    return Block(booking=booking, start_minutes=lo, end_minutes=hi, label=label)


def _assign_lanes(blocks: list[Block]) -> None:
    """Greedy lanes; a block shares its width only with blocks it overlaps."""
    blocks.sort(key=lambda b: (b.start_minutes, -b.end_minutes))
    lane_ends: list[int] = []
    for block in blocks:
        for index, ends in enumerate(lane_ends):
            if ends <= block.start_minutes:
                block.lane = index
                lane_ends[index] = block.end_minutes
                break
        else:
            block.lane = len(lane_ends)
            lane_ends.append(block.end_minutes)
    for block in blocks:
        overlapping = [
            o for o in blocks
            if o.start_minutes < block.end_minutes and o.end_minutes > block.start_minutes
        ]
        block.lanes = max(o.lane for o in overlapping) + 1


def week(monday: dt.date, *, kinds: set[str], term: str = "") -> dict:
    opens, closes = window()
    span = closes - opens
    today = timezone.localdate()
    days = [Day(date=monday + dt.timedelta(days=i), is_today=False) for i in range(7)]
    for day in days:
        day.is_today = day.date == today
    rows = bookings_between(monday, monday + dt.timedelta(days=7), kinds=kinds, term=term)
    for day in days:
        day.blocks = [b for b in (_clip(r, day.date, opens, closes) for r in rows) if b]
        _assign_lanes(day.blocks)
        for block in day.blocks:
            block.top = round((block.start_minutes - opens) / span * 100, 3)
            block.height = round((block.end_minutes - block.start_minutes) / span * 100, 3)
            share = 100 / block.lanes
            block.left = round(block.lane * share + 1, 3)
            block.width = round(share - 2, 3)
    now = timezone.localtime()
    now_minutes = now.hour * 60 + now.minute
    return {
        "days": days,
        "bookings": rows,
        "hours": _hour_marks(opens, closes),
        "span_hours": span / 60,
        "now_top": round((now_minutes - opens) / span * 100, 3)
        if opens <= now_minutes <= closes else None,
    }


def by_room(day: dt.date, *, kinds: set[str], term: str = "") -> dict:
    """One row per active resource for one day, Teams room-finder style."""
    opens, closes = window()
    span = closes - opens
    rows = bookings_between(day, day + dt.timedelta(days=1), kinds=kinds, term=term)
    resources = (
        Resource.objects.filter(
            resource_type__in=[KINDS[k] for k in kinds], status=ResourceStatus.ACTIVE
        )
        .select_related("venue", "vehicle")
        .order_by("resource_type", "venue__display_order", "name")
    )
    by_resource: dict[int, list[Block]] = {}
    for booking in rows:
        block = _clip(booking, day, opens, closes)
        if block:
            block.left = round((block.start_minutes - opens) / span * 100, 3)
            block.width = round((block.end_minutes - block.start_minutes) / span * 100, 3)
            by_resource.setdefault(booking.resource_id, []).append(block)
    return {
        "rooms": [
            {"resource": r, "blocks": by_resource.get(r.pk, [])} for r in resources
        ],
        "bookings": rows,
        "hours": _hour_marks(opens, closes),
        "span_hours": span / 60,
    }


def _hour_marks(opens: int, closes: int) -> list[dict]:
    span = closes - opens
    marks = []
    minute = opens - opens % 60 + (60 if opens % 60 else 0)
    while minute < closes:
        marks.append({"label": f"{minute // 60:02d}:00", "top": round((minute - opens) / span * 100, 3)})
        minute += 60
    return marks


def mini_month(anchor: dt.date, *, week_start: dt.date) -> dict:
    """A month grid for the side column; days in the shown week are marked."""
    today = timezone.localdate()
    cal = pycal.Calendar(firstweekday=0)
    cells = []
    for day in cal.itermonthdates(anchor.year, anchor.month):
        cells.append({
            "date": day,
            "monday": monday_of(day),
            "out": day.month != anchor.month,
            "today": day == today,
            "in_range": week_start <= day < week_start + dt.timedelta(days=7),
        })
    return {"label": anchor.strftime("%B %Y"), "cells": cells}


def waiting_for_decision(limit: int = 8):
    """Requests still to decide, soonest first, for the side column."""
    return list(
        Booking.objects.filter(status=BookingStatus.PENDING, end_at__gte=timezone.now())
        .select_related("resource")
        .order_by("start_at")[:limit]
    ), Booking.objects.filter(status=BookingStatus.PENDING, end_at__gte=timezone.now()).count()
