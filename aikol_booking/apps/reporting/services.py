"""Aggregations for the Insights screen.

Most figures are read with one narrow query each and summed in Python. The
periods are a semester at most a year, which is a few thousand rows, and doing
the arithmetic here keeps the part-hour, local-date and opening-hour rules in one
readable place instead of spread across database-specific SQL.

Every figure covers a period that ends today at the latest, and is compared with
the previous period of the same length: comparing half a semester with the whole
of the last one would always read as a fall.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db.models import Count, F, Min, Q, QuerySet
from django.utils import timezone

from apps.bookings.keys import outstanding_keys
from apps.bookings.models import (
    BLOCKING_STATUSES,
    AcademicTerm,
    Booking,
    BookingStatus,
    KeyHandover,
    ManagementDecision,
    Via,
)
from apps.resources.models import ResourceStatus, ResourceType, Vehicle, Venue

#: The bookable window, and therefore the heatmap's rows.
WINDOW_START, WINDOW_END = 8, 22

#: Statuses that represent a booking that actually happened or will.
HONOURED = (BookingStatus.APPROVED, BookingStatus.COMPLETED)

#: Users cancel their own bookings up to this many days before; inside it the
#: office has to do it (project record §5), so these are the late ones.
LATE_CANCEL_DAYS = 3

PERIODS = (("month", "This month"), ("semester", "This semester"), ("year", "Last 12 months"))


# --- Periods ---------------------------------------------------------------


@dataclass
class Period:
    kind: str
    start: dt.date
    end: dt.date  # inclusive, never after today
    label: str
    compare_label: str = ""
    term: AcademicTerm | None = None
    previous: "Period | None" = field(default=None, repr=False)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def begin(self) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(self.start, dt.time.min))

    @property
    def finish(self) -> dt.datetime:
        """Exclusive: midnight after the last day."""
        return timezone.make_aware(dt.datetime.combine(self.end + dt.timedelta(days=1), dt.time.min))

    def within(self, field_name: str) -> Q:
        return Q(**{f"{field_name}__gte": self.begin, f"{field_name}__lt": self.finish})


def _span(start: dt.date, end: dt.date) -> str:
    # `%-d` is not portable to Windows, hence `.day`.
    if start.year == end.year:
        return f"{start.day} {start:%b} to {end.day} {end:%b %Y}"
    return f"{start.day} {start:%b %Y} to {end.day} {end:%b %Y}"


def _same_length_before(period: Period) -> Period:
    end = period.start - dt.timedelta(days=1)
    start = end - dt.timedelta(days=period.days - 1)
    return Period("previous", start, end, _span(start, end))


def started_terms(today: dt.date) -> list[AcademicTerm]:
    """Semesters that have begun, latest first; a future one has nothing to show."""
    return list(AcademicTerm.objects.filter(start_date__lte=today).order_by("-start_date")[:12])


def _parse_date(value: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def resolve_period(params, today: dt.date, terms: list[AcademicTerm]) -> Period:
    """The period the screen shows, from the query string.

    Falls back rather than failing: a stale bookmark with a deleted semester or
    a mistyped date still opens the page.
    """
    kind = params.get("period") or ("semester" if terms else "year")

    if kind == "custom":
        start, end = _parse_date(params.get("from")), _parse_date(params.get("to"))
        if start and end:
            end = min(end, today)
            start = max(min(start, end), end - dt.timedelta(days=3 * 366))
            period = Period("custom", start, end, _span(start, end), "the period before")
            period.previous = _same_length_before(period)
            return period
        kind = "semester" if terms else "year"

    if kind == "semester" and terms:
        chosen = None
        if params.get("term", "").isdigit():
            chosen = next((t for t in terms if t.pk == int(params["term"])), None)
        term = chosen or AcademicTerm.for_date(today) or terms[0]
        end = min(term.end_date, today)
        period = Period("semester", term.start_date, end, term.name, "last semester", term=term)
        earlier = next((t for t in terms if t.end_date < term.start_date), None)
        if earlier:
            prev_end = min(earlier.end_date, earlier.start_date + dt.timedelta(days=period.days - 1))
            period.previous = Period("previous", earlier.start_date, prev_end, earlier.name)
        else:
            period.previous = _same_length_before(period)
            period.compare_label = "the period before"
        return period

    if kind == "month":
        start = today.replace(day=1)
        period = Period("month", start, today, f"{today:%B %Y}", "last month")
        prev_start = (start - dt.timedelta(days=1)).replace(day=1)
        prev_end = min(prev_start + dt.timedelta(days=period.days - 1), start - dt.timedelta(days=1))
        period.previous = Period("previous", prev_start, prev_end, f"{prev_start:%B %Y}")
        return period

    start = today - dt.timedelta(days=364)
    period = Period("year", start, today, "Last 12 months", "the 12 months before")
    period.previous = _same_length_before(period)
    return period


# --- Comparison wording ------------------------------------------------------


def duration(hours: float) -> str:
    """Hours while a wait is under two days; days after that, which read better."""
    if hours >= 48:
        return f"{round(hours / 24, 1):g} days"
    return f"{round(hours, 1):g} h"


def compare(value, previous, *, unit: str = "count", higher_is_good: bool = True,
            label: str = "") -> dict:
    """A figure with its change on the previous period, worded for a first-time reader."""
    out = {"value": value, "previous": previous, "text": "", "tone": "flat"}
    if value is None or previous is None:
        out["text"] = "Nothing to compare with" if previous is None else ""
        return out
    diff = value - previous
    if unit == "percent_points":
        size = round(abs(diff))
        if size == 0:
            out["text"] = f"Same as {label}"
            return out
        out["text"] = f"{'Up' if diff > 0 else 'Down'} {size} point{'s' if size != 1 else ''}"
    elif unit == "hours":
        if round(abs(diff), 1) == 0:
            out["text"] = f"Same as {label}"
            return out
        out["text"] = f"{'Slower' if diff > 0 else 'Faster'} by {duration(abs(diff))}"
    else:
        if diff == 0:
            out["text"] = f"Same as {label}"
            return out
        if previous:
            out["text"] = f"{'Up' if diff > 0 else 'Down'} {round(abs(diff) / previous * 100)}% on {label}"
        else:
            out["text"] = f"Up from none on {label}"
    out["tone"] = "good" if (diff > 0) == higher_is_good else "bad"
    return out


# --- Shared readings ---------------------------------------------------------


def period_bookings(start: dt.date, end: dt.date) -> QuerySet[Booking]:
    begin = timezone.make_aware(dt.datetime.combine(start, dt.time.min))
    finish = timezone.make_aware(dt.datetime.combine(end, dt.time.max))
    return Booking.objects.filter(start_at__gte=begin, start_at__lte=finish)


def _hours(start: dt.datetime, end: dt.datetime) -> float:
    return (end - start).total_seconds() / 3600


def _trip_days(start: dt.datetime, end: dt.datetime) -> int:
    return max(1, (timezone.localtime(end).date() - timezone.localtime(start).date()).days + 1)


def _open_hours(venue: Venue) -> float:
    opens = venue.opens_at.hour + venue.opens_at.minute / 60
    closes = venue.closes_at.hour + venue.closes_at.minute / 60
    return max(closes - opens, 0)


def _decisions(period: Period) -> list[tuple]:
    """Office decisions made in the period on requests that waited for one.

    A booking the deciding officer entered themselves is approved as it is
    made; counting it would flatter both the approval rate and the time taken.
    """
    return list(
        Booking.objects.filter(period.within("decided_at"), decided_at__isnull=False)
        .exclude(decided_by_id=None)
        .exclude(created_by_id__isnull=False, decided_by_id=F("created_by_id"))
        .values_list("created_at", "decided_at", "status", "decision_reason")
    )


def _late(cancelled_at: dt.datetime, start_at: dt.datetime) -> bool:
    return cancelled_at > start_at - dt.timedelta(days=LATE_CANCEL_DAYS)


def _headline(period: Period, venues: list[Venue]) -> dict:
    """The six figures in the strip, for one period."""
    rows = list(
        Booking.objects.filter(period.within("start_at")).values_list(
            "status", "start_at", "end_at", "resource__resource_type", "resource_id"
        )
    )
    open_by_venue = {v.pk: _open_hours(v) for v in venues}
    room_hours = 0.0
    trip_days = 0
    for status, start, end, kind, resource_id in rows:
        if status not in HONOURED:
            continue
        if kind == ResourceType.VENUE:
            if resource_id in open_by_venue:
                room_hours += _hours(start, end)
        else:
            trip_days += _trip_days(start, end)
    capacity = sum(open_by_venue.values()) * period.days

    decisions = _decisions(period)
    rejected = sum(1 for row in decisions if row[2] == BookingStatus.REJECTED)
    waits = [_hours(created, decided) for created, decided, *_ in decisions if decided >= created]

    cancelled = Booking.objects.filter(
        period.within("cancelled_at"), status=BookingStatus.CANCELLED
    ).values_list("cancelled_at", "start_at")

    return {
        "bookings": len(rows),
        "room_use": round(room_hours / capacity * 100) if capacity else None,
        "decide_hours": round(statistics.fmean(waits), 1) if waits else None,
        "approved": round((len(decisions) - rejected) / len(decisions) * 100) if decisions else None,
        "late_cancellations": sum(1 for c, s in cancelled if _late(c, s)),
        "trip_days": trip_days,
    }


def kpis(period: Period, venues: list[Venue]) -> list[dict]:
    now = _headline(period, venues)
    before = _headline(period.previous, venues) if period.previous else {}
    label = period.compare_label or "the period before"

    def row(key, title, *, suffix="", **kw):
        figure = compare(now[key], before.get(key), label=label, **kw)
        value = now[key]
        if value is None:
            shown = "None"
        elif kw.get("unit") == "hours":
            shown = duration(value)
        else:
            shown = f"{value}{suffix}"
        figure.update(title=title, shown=shown)
        return figure

    return [
        row("bookings", "Bookings"),
        row("room_use", "Room Use", suffix="%", unit="percent_points"),
        row("decide_hours", "Average Time to Decide", unit="hours",
            higher_is_good=False),
        row("approved", "Approved", suffix="%", unit="percent_points"),
        row("late_cancellations", "Late Cancellations", higher_is_good=False),
        row("trip_days", "Car Trip Days"),
    ]


# --- Needs attention (now, whatever the period) ------------------------------


def attention(vehicles: list[Vehicle], today: dt.date) -> list[dict]:
    now = timezone.now()
    out = []

    waiting = Booking.objects.filter(status=BookingStatus.PENDING).aggregate(
        n=Count("id"), oldest=Min("created_at")
    )
    if waiting["n"]:
        days = (today - timezone.localtime(waiting["oldest"]).date()).days
        since = "today" if days == 0 else f"{days} day{'s' if days != 1 else ''}"
        out.append({
            "tone": "red" if days >= 2 else "amber",
            "figure": waiting["n"],
            "text": f"request{'s' if waiting['n'] != 1 else ''} awaiting a decision, "
                    f"oldest waiting {since}",
            "url": "bookings:approvals",
        })

    overdue = Counter(
        outstanding_keys().filter(booking__end_at__lt=now)
        .values_list("booking__resource__resource_type", flat=True)
    )
    if overdue:
        parts = []
        if overdue[ResourceType.VENUE]:
            parts.append(f"{overdue[ResourceType.VENUE]} venue")
        if overdue[ResourceType.VEHICLE]:
            parts.append(f"{overdue[ResourceType.VEHICLE]} car")
        total = sum(overdue.values())
        out.append({
            "tone": "amber",
            "figure": total,
            "text": f"key{'s' if total != 1 else ''} overdue now ({' and '.join(parts)})",
            "url": "bookings:keys",
        })

    trips = Booking.objects.filter(
        status__in=BLOCKING_STATUSES, management_status=ManagementDecision.PENDING,
        end_at__gte=now,
    ).count()
    if trips:
        out.append({
            "tone": "amber",
            "figure": trips,
            "text": f"car trip{'s' if trips != 1 else ''} waiting for Kulliyyah management",
            "url": "bookings:manage",
        })

    if vehicles:
        car = min(vehicles, key=lambda v: v.road_tax_expiry)
        days = (car.road_tax_expiry - today).days
        if days < 0:
            text, tone = f"expired {-days} day{'s' if days != -1 else ''} ago ({car.name})", "red"
        else:
            text = f"next renewal in {days} day{'s' if days != 1 else ''} ({car.name})"
            tone = "amber" if days <= 30 else "green"
        out.append({"tone": tone, "figure": None, "text": f"Road tax: {text}",
                    "url": "resources:manage_vehicles"})
    return out


# --- Venues ------------------------------------------------------------------


def venue_use(period: Period, venues: list[Venue]) -> dict:
    """Room use by building and by room, against each room's own opening hours."""
    booked: dict[int, float] = defaultdict(float)
    groups: dict[int, list[int]] = defaultdict(list)
    for resource_id, start, end, attendees in Booking.objects.filter(
        period.within("start_at"), status__in=HONOURED,
        resource__resource_type=ResourceType.VENUE,
    ).values_list("resource_id", "start_at", "end_at", "attendees"):
        booked[resource_id] += _hours(start, end)
        if attendees:
            groups[resource_id].append(attendees)

    rooms, buildings, fit = [], {}, []
    for venue in venues:
        capacity = _open_hours(venue) * period.days
        percent = min(100, round(booked[venue.pk] / capacity * 100)) if capacity else 0
        rooms.append({"name": venue.name, "percent": percent, "low": percent < 10})
        name = venue.building.name if venue.building_id else "No building"
        total = buildings.setdefault(name, [0.0, 0.0])
        total[0] += booked[venue.pk]
        total[1] += capacity
        if groups[venue.pk]:
            usual = round(statistics.median(groups[venue.pk]))
            share = usual / venue.capacity
            if share > 1:
                verdict, tone = "Over the seats", "bad"
            elif share < 0.3:
                verdict, tone = "Often too big", "warn"
            else:
                verdict, tone = "Good fit", "ok"
            fit.append({
                "name": venue.name, "seats": venue.capacity, "usual": usual,
                "count": len(groups[venue.pk]), "verdict": verdict, "tone": tone, "share": share,
            })

    by_building = [
        {"name": name, "percent": min(100, round(h / cap * 100)) if cap else 0}
        for name, (h, cap) in buildings.items()
    ]
    order = {"warn": 0, "bad": 1, "ok": 2}
    return {
        "buildings": sorted(by_building, key=lambda r: -r["percent"]),
        "rooms": sorted(rooms, key=lambda r: -r["percent"]),
        "fit": sorted(fit, key=lambda r: (order[r["tone"]], r["share"]))[:10],
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


def monthly_volume(period: Period, today: dt.date, months: int = 12) -> list[dict]:
    """Bookings by the month they take place, with the period's months marked.

    One query: the months are counted here from local dates, so a booking at
    00:30 on the 1st is not filed under the month before by a UTC truncation.
    """
    first = today.replace(day=1)
    keys = []
    year, month = first.year, first.month
    for _ in range(months):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    since = timezone.make_aware(dt.datetime(keys[0][0], keys[0][1], 1))
    after = dt.date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    until = timezone.make_aware(dt.datetime.combine(after, dt.time.min))
    counts: Counter = Counter()
    for start in Booking.objects.filter(start_at__gte=since, start_at__lt=until).values_list(
        "start_at", flat=True
    ):
        local = timezone.localtime(start)
        counts[(local.year, local.month)] += 1
    peak = max(counts.values(), default=0) or 1
    out = []
    for year, month in keys:
        day = dt.date(year, month, 1)
        in_period = period.start.replace(day=1) <= day <= period.end
        out.append({
            "label": f"{day:%b}", "year": year, "count": counts[(year, month)],
            "percent": round(counts[(year, month)] / peak * 100), "current": in_period,
        })
    return out


# --- Vehicles ------------------------------------------------------------------


def vehicle_use(period: Period, vehicles: list[Vehicle]) -> dict:
    days: dict[int, int] = defaultdict(int)
    places: Counter = Counter()
    shown: dict[str, str] = {}
    for resource_id, start, end, where in Booking.objects.filter(
        period.within("start_at"), status__in=HONOURED,
        resource__resource_type=ResourceType.VEHICLE,
    ).values_list("resource_id", "start_at", "end_at", "location_to"):
        days[resource_id] += _trip_days(start, end)
        name = " ".join((where or "").split())
        if name:
            # Typed by hand, so "Putrajaya" and "putrajaya " are one place.
            key = name.casefold()
            places[key] += 1
            shown.setdefault(key, name)

    distance: dict[int, int] = defaultdict(int)
    for resource_id, out_km, in_km in KeyHandover.objects.filter(
        period.within("issued_at"), booking__resource__resource_type=ResourceType.VEHICLE,
        mileage_out__isnull=False, mileage_in__isnull=False,
    ).values_list("booking__resource_id", "mileage_out", "mileage_in"):
        if in_km >= out_km:
            distance[resource_id] += in_km - out_km

    top = places.most_common(6)
    peak = top[0][1] if top else 1
    management = list(
        Booking.objects.filter(period.within("management_decided_at"))
        .exclude(management_status__in=("", ManagementDecision.PENDING))
        .values_list("management_status", "decided_at", "management_decided_at")
    )
    approved = sum(1 for status, *_ in management if status == ManagementDecision.APPROVED)
    waits = [(m - d).total_seconds() / 86400 for _, d, m in management if d and m >= d]
    return {
        "cars": [
            {"name": v.name, "registration": v.registration_number, "days": days[v.pk],
             "distance": distance.get(v.pk), "road_tax": v.road_tax_expiry}
            for v in vehicles
        ],
        "places": [
            {"name": shown[key], "count": n, "percent": round(n / peak * 100)} for key, n in top
        ],
        "management": {
            "total": len(management),
            "approved": round(approved / len(management) * 100) if management else None,
            "declined": round((len(management) - approved) / len(management) * 100)
            if management else None,
            "wait_days": round(statistics.median(waits), 1) if waits else None,
        },
    }


# --- Office work ---------------------------------------------------------------


def office_work(period: Period) -> dict:
    decisions = _decisions(period)
    buckets = [0, 0, 0]
    for created, decided, *_ in decisions:
        gap = (timezone.localtime(decided).date() - timezone.localtime(created).date()).days
        buckets[min(max(gap, 0), 2)] += 1
    total = len(decisions)
    speed = [
        {"name": name, "count": n, "percent": round(n / total * 100) if total else 0}
        for name, n in zip(("Same day", "Next day", "Two days or more"), buckets)
    ]

    reasons: Counter = Counter()
    shown: dict[str, str] = {}
    for *_, status, reason in decisions:
        if status != BookingStatus.REJECTED:
            continue
        text = " ".join((reason or "").split()).rstrip(".") or "No reason given"
        key = text.casefold()
        reasons[key] += 1
        shown.setdefault(key, text)
    top = reasons.most_common(6)
    peak = top[0][1] if top else 1

    keys = list(
        KeyHandover.objects.filter(period.within("issued_at")).values_list(
            "issue_via", "returned_at", "booking__end_at"
        )
    )
    late = sum(1 for _, back, end in keys if back and back > end)
    kiosk = sum(1 for via, *_ in keys if via == Via.KIOSK)
    never = (
        Booking.objects.filter(period.within("end_at"), status=BookingStatus.COMPLETED)
        .filter(Q(key_handover__isnull=True) | Q(key_handover__issued_at__isnull=True))
        .count()
    )

    early = late_cancel = 0
    for cancelled, start in Booking.objects.filter(
        period.within("cancelled_at"), status=BookingStatus.CANCELLED
    ).values_list("cancelled_at", "start_at"):
        if _late(cancelled, start):
            late_cancel += 1
        else:
            early += 1
    cancelled_total = early + late_cancel

    return {
        "decided": total,
        "speed": speed,
        "reasons": [
            {"name": shown[key], "count": n, "percent": round(n / peak * 100)} for key, n in top
        ],
        "keys": {
            "issued": len(keys),
            "late": late,
            "late_percent": round(late / len(keys) * 100) if keys else 0,
            "never": never,
            "kiosk_percent": round(kiosk / len(keys) * 100) if keys else None,
        },
        "cancellations": {
            "early": early,
            "late": late_cancel,
            "early_percent": round(early / cancelled_total * 100) if cancelled_total else 0,
            "late_percent": round(late_cancel / cancelled_total * 100) if cancelled_total else 0,
        },
    }


# --- Who books -----------------------------------------------------------------


def by_affiliation(bookings: QuerySet[Booking]) -> list[dict]:
    from apps.accounts.models import Affiliation

    counts = dict(
        bookings.values_list("user__affiliation").annotate(n=Count("id"))
        .values_list("user__affiliation", "n")
    )
    total = sum(counts.values())
    return [
        {"key": value.lower(), "name": label, "count": counts.get(value, 0),
         "percent": round(counts.get(value, 0) / total * 100) if total else 0}
        for value, label in Affiliation.choices
        if counts.get(value)
    ]


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


def active_venues() -> list[Venue]:
    return list(Venue.objects.filter(status=ResourceStatus.ACTIVE).select_related("building"))


def active_vehicles() -> list[Vehicle]:
    return list(Vehicle.objects.filter(status=ResourceStatus.ACTIVE))
