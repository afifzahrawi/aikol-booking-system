"""The office's booking calendar: a week of days, or one day by room.

Laid out like a desktop calendar (Google Calendar, Teams). Every position is a
percentage of the bookable window, computed here so the template only places
boxes: a booking's top and height within its day column, or its left and width
along a room's row.

Two things kept the week unreadable on a busy week, and are handled here. A
booking running over more than one day (a car trip, mostly) filled whole day
columns; it is drawn instead as a bar in the Trips lane above the hours, like
an all-day event. And five overlapping bookings became five slivers; at most
`MAX_LANES` sit side by side, the rest are counted as "+n more" on a booking
they overlap and listed in that day's agenda.
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
MAX_LANES = 2
VEHICLE_GROUP = "Kulliyyah Vehicles"


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
    hidden: int = 0  # overlapping bookings counted on this one as "+n more"

    @property
    def is_vehicle(self) -> bool:
        return self.booking.resource.resource_type == ResourceType.VEHICLE

    @property
    def is_pending(self) -> bool:
        return self.booking.status == BookingStatus.PENDING

    @property
    def more_top(self) -> float:
        return round(self.top + self.height, 3)

    @property
    def more_left(self) -> float:
        return round(self.left + self.width, 3)


@dataclass
class Trip:
    """A booking over more than one day, as a bar across the Trips lane."""

    booking: Booking
    first: int  # column of the first day shown, 0 for Monday
    last: int
    row: int = 0
    starts_before: bool = False
    ends_after: bool = False

    @property
    def is_vehicle(self) -> bool:
        return self.booking.resource.resource_type == ResourceType.VEHICLE

    @property
    def is_pending(self) -> bool:
        return self.booking.status == BookingStatus.PENDING

    @property
    def grid(self) -> str:
        """Grid placement as custom properties; column 1 holds the lane's label."""
        return f"--from:{self.first + 2};--to:{self.last + 3};--row:{self.row + 1}"


@dataclass
class Day:
    date: dt.date
    is_today: bool
    blocks: list[Block] = field(default_factory=list)
    agenda: list[Booking] = field(default_factory=list)  # everything on this day

    @property
    def key(self) -> str:
        return self.date.isoformat()


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
        block.lanes = min(max(o.lane for o in overlapping) + 1, MAX_LANES)


def _overlaps(a: Block, b: Block) -> bool:
    return a.start_minutes < b.end_minutes and a.end_minutes > b.start_minutes


def _cap_lanes(blocks: list[Block]) -> list[Block]:
    """Blocks beyond `MAX_LANES` are counted on a shown block they overlap,
    preferring the one beside where they would have gone."""
    shown = [b for b in blocks if b.lane < MAX_LANES]
    for extra in (b for b in blocks if b.lane >= MAX_LANES):
        hosts = [s for s in shown if _overlaps(s, extra)]
        if hosts:
            max(hosts, key=lambda s: s.lane).hidden += 1
    return shown


def _last_day(booking: Booking) -> dt.date:
    """The last date a booking occupies; one ending at midnight ends the day before."""
    end = timezone.localtime(booking.end_at)
    return (end - dt.timedelta(microseconds=1)).date()


def _is_trip(booking: Booking) -> bool:
    return timezone.localtime(booking.start_at).date() < _last_day(booking)


def _trips(rows: list[Booking], monday: dt.date) -> tuple[list[Trip], int]:
    """Multi-day bookings packed into as few rows as possible."""
    sunday = monday + dt.timedelta(days=6)
    trips = []
    for booking in rows:
        if not _is_trip(booking):
            continue
        first = timezone.localtime(booking.start_at).date()
        last = _last_day(booking)
        trips.append(Trip(
            booking=booking,
            first=max(0, (first - monday).days),
            last=min(6, (last - monday).days),
            starts_before=first < monday,
            ends_after=last > sunday,
        ))
    trips.sort(key=lambda t: (t.first, -t.last))
    row_ends: list[int] = []
    for trip in trips:
        for index, ends in enumerate(row_ends):
            if ends < trip.first:
                trip.row, row_ends[index] = index, trip.last
                break
        else:
            trip.row = len(row_ends)
            row_ends.append(trip.last)
    return trips, len(row_ends)


def week(monday: dt.date, *, kinds: set[str], term: str = "") -> dict:
    opens, closes = window()
    span = closes - opens
    today = timezone.localdate()
    days = [Day(date=monday + dt.timedelta(days=i), is_today=False) for i in range(7)]
    for day in days:
        day.is_today = day.date == today
    rows = bookings_between(monday, monday + dt.timedelta(days=7), kinds=kinds, term=term)
    trips, trip_rows = _trips(rows, monday)
    hourly = [r for r in rows if not _is_trip(r)]
    for day in days:
        day.agenda = [
            r for r in rows
            if timezone.localtime(r.start_at).date() <= day.date <= _last_day(r)
        ]
        blocks = [b for b in (_clip(r, day.date, opens, closes) for r in hourly) if b]
        _assign_lanes(blocks)
        day.blocks = _cap_lanes(blocks)
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
        "trips": trips,
        "trip_rows": trip_rows,
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
        .select_related("venue__building", "vehicle")
        .order_by(
            "-resource_type",  # VENUE before VEHICLE: rooms first, the cars last
            "venue__building__display_order",
            "venue__building__name",
            "venue__display_order",
            "name",
        )
    )
    by_resource: dict[int, list[Block]] = {}
    for booking in rows:
        block = _clip(booking, day, opens, closes)
        if block:
            block.left = round((block.start_minutes - opens) / span * 100, 3)
            block.width = round((block.end_minutes - block.start_minutes) / span * 100, 3)
            by_resource.setdefault(booking.resource_id, []).append(block)
    # Grouped by building, as the room picker is, so a long list of rooms
    # reads in the order people walk the Kulliyyah.
    groups: list[dict] = []
    for resource in resources:
        if resource.resource_type == ResourceType.VEHICLE:
            name = VEHICLE_GROUP
        else:
            building = getattr(getattr(resource, "venue", None), "building", None)
            name = building.name if building else "Other Venues"
        if not groups or groups[-1]["name"] != name:
            groups.append({"name": name, "rooms": []})
        groups[-1]["rooms"].append(
            {"resource": resource, "blocks": by_resource.get(resource.pk, [])}
        )
    return {
        "groups": groups,
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
