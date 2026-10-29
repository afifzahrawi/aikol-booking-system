"""The venue and vehicle picker: what is free when the person needs it.

The lists used to be a paged catalogue with a separate Apply button. People do
not browse rooms, they look for one that is free at a time and fits their
group, so the picker answers that: every resource carries its state for the
chosen period, free ones come first and the smallest room that fits leads.

It is not paged. AIKOL's catalogue is a few dozen rooms and a handful of cars,
and the page groups venues by building with each group collapsed to one row,
which does the job paging did without splitting a building across pages. Every
filter still runs in the query; the bookings that decide the states are read in
one query for all resources together.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.db.models import Prefetch, Q
from django.utils import timezone

from .models import (
    Resource,
    ResourceImage,
    ResourceStatus,
    ResourceType,
    Vehicle,
    Venue,
    VenueType,
)

# A group shows this many before "Show all"; the list view fits more per row.
GROUP_PREVIEW = {"grid": 4, "list": 6}
RECENT_COUNT = 3

FREE, BUSY, OFF = "free", "busy", "off"


@dataclass
class Pick:
    resource: Resource
    state: str
    label: str
    best_fit: bool = False


@dataclass
class PickGroup:
    name: str
    slug: str
    picks: list[Pick] = field(default_factory=list)


def _time(raw: str | None) -> dt.time | None:
    try:
        return dt.time.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _date(raw: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def half_hour_slots(window_start: str, window_end: str) -> list[str]:
    hour, minute = (int(part) for part in window_start.split(":"))
    end = tuple(int(part) for part in window_end.split(":"))
    slots = []
    while (hour, minute) <= end:
        slots.append(f"{hour:02d}:{minute:02d}")
        minute += 30
        if minute >= 60:
            minute, hour = minute - 60, hour + 1
    return slots


def default_period(slots: list[str], now: dt.datetime) -> tuple[dt.date, str, str]:
    """The next half hour today, two hours long, or tomorrow morning when
    today's window has nearly gone. A first visit then already answers
    "what is free soon"."""
    today = now.date()
    later = [slot for slot in slots if slot > now.strftime("%H:%M")]
    if len(later) >= 3:
        start = later[0]
        index = slots.index(start)
        return today, start, slots[min(index + 4, len(slots) - 1)]
    return today + dt.timedelta(days=1), slots[0], slots[min(4, len(slots) - 1)]


def _states(
    resources: list[Resource], start_at: dt.datetime | None, end_at: dt.datetime | None
) -> dict[int, tuple[str, str]]:
    """Each resource's state for the period, from one bookings query."""
    from apps.bookings.models import BLOCKING_STATUSES, Booking

    busy_until: dict[int, dt.datetime] = {}
    if start_at and end_at:
        overlaps = Booking.objects.filter(
            resource_id__in=[r.pk for r in resources],
            status__in=BLOCKING_STATUSES,
            start_at__lt=end_at,
            end_at__gt=start_at,
        ).values_list("resource_id", "end_at")
        for resource_id, ends in overlaps:
            if resource_id not in busy_until or ends > busy_until[resource_id]:
                busy_until[resource_id] = ends
    states = {}
    for resource in resources:
        if resource.status != ResourceStatus.ACTIVE:
            label = (
                "Not in service"
                if resource.resource_type == ResourceType.VEHICLE
                else "Under maintenance"
            )
            states[resource.pk] = (OFF, label)
        elif resource.pk in busy_until:
            ends = timezone.localtime(busy_until[resource.pk])
            same_day = start_at and ends.date() == timezone.localtime(start_at).date()
            states[resource.pk] = (
                BUSY,
                f"Booked until {ends:%H:%M}" if same_day else f"Booked until {ends:%d %b}",
            )
        elif start_at:
            local_start, local_end = timezone.localtime(start_at), timezone.localtime(end_at)
            states[resource.pk] = (FREE, f"Free {local_start:%H:%M} to {local_end:%H:%M}")
        else:
            states[resource.pk] = (FREE, "Available")
    return states


def build_picker(request, kind: str) -> dict:
    """Everything the picker template needs, read from the GET parameters."""
    from apps.administration.models import SystemSetting
    from apps.bookings.models import Booking
    from apps.bookings.services import validate_period

    is_vehicle = kind == ResourceType.VEHICLE
    window_start = SystemSetting.get("bookable_window_start")
    window_end = SystemSetting.get("bookable_window_end")
    slots = half_hour_slots(window_start, window_end)
    params = request.GET

    default_date, default_from, default_until = default_period(slots, timezone.localtime())
    date = _date(params.get("date")) or default_date
    end_date = (_date(params.get("end_date")) or date) if is_vehicle else date
    from_time = params.get("from") if params.get("from") in slots else default_from
    until_time = params.get("until") if params.get("until") in slots else default_until
    # Everything is shown until the person asks for free ones only (office
    # request, 29 October 2026): a first visit should show every room.
    free_only = params.get("free") == "1"
    term = (params.get("q") or "").strip()
    people_raw = params.get("people") or params.get("capacity") or ""
    people = int(people_raw) if people_raw.isdigit() and 0 < int(people_raw) < 1000 else 0
    chosen_types = [code for code in params.getlist("type") if code]

    start_at = timezone.make_aware(dt.datetime.combine(date, _time(from_time)))
    end_at = timezone.make_aware(dt.datetime.combine(end_date, _time(until_time)))

    images = Prefetch("images", queryset=ResourceImage.objects.order_by("display_order", "id"))
    if is_vehicle:
        pool = Vehicle.objects.filter(road_tax_expiry__gte=timezone.localdate())
        size_field, search = "seats", ("name", "code", "make", "model", "registration_number")
    else:
        pool = Venue.objects.select_related("venue_type", "building").prefetch_related(
            "facilities"
        )
        size_field = "capacity"
        search = ("name", "code", "location", "building__name", "facilities__name")
    pool = pool.prefetch_related(images)

    # The period rules (past, opening window, length) are the same for every
    # resource of a kind, so they are checked once and shown once.
    sample = pool.first()
    problems = validate_period(sample, start_at, end_at) if sample else []
    problems = [p for p in problems if not p.endswith("is not available for that period.")]
    period_ok = not problems

    queryset = pool
    if term:
        matches = Q()
        for name in search:
            matches |= Q(**{f"{name}__icontains": term})
        queryset = queryset.filter(matches).distinct()
    if people:
        queryset = queryset.filter(**{f"{size_field}__gte": people})
    if chosen_types and not is_vehicle:
        queryset = queryset.filter(venue_type_id__in=chosen_types)
    resources = list(queryset)

    recent_ids = []
    for resource_id in (
        Booking.objects.filter(user=request.user, resource__resource_type=kind)
        .order_by("-created_at")
        .values_list("resource_id", flat=True)[:30]
    ):
        if resource_id not in recent_ids:
            recent_ids.append(resource_id)
        if len(recent_ids) == RECENT_COUNT:
            break
    by_pk = {r.pk: r for r in resources}
    missing = [pk for pk in recent_ids if pk not in by_pk]
    recent_pool = by_pk | {r.pk: r for r in pool.filter(pk__in=missing)} if missing else by_pk

    states = _states(
        list(recent_pool.values()),
        start_at if period_ok else None,
        end_at if period_ok else None,
    )

    picks = [Pick(r, *states[r.pk]) for r in resources]
    if free_only and period_ok:
        picks = [p for p in picks if p.state == FREE]

    def order(pick: Pick):
        size = getattr(pick.resource, size_field)
        if people:
            rank = {FREE: 0, BUSY: 1, OFF: 2}[pick.state]
            return (rank, size, pick.resource.name)
        # The Admin's own order; each card already says whether it is free.
        return (pick.resource.display_order, pick.resource.name)

    picks.sort(key=order)

    groups: list[PickGroup] = []
    if is_vehicle:
        groups.append(PickGroup("Kulliyyah Vehicles", "vehicles", picks))
    else:
        index: dict[str, PickGroup] = {}
        # sorted() is stable, so the order inside each building is kept.
        ordered = sorted(
            picks,
            key=lambda p: (
                (p.resource.building.display_order, p.resource.building.name)
                if p.resource.building_id
                else (10**6, "")
            ),
        )
        for pick in ordered:
            name = pick.resource.building.name if pick.resource.building_id else "Other"
            if name not in index:
                index[name] = PickGroup(name, f"building-{pick.resource.building_id or 0}")
                groups.append(index[name])
            index[name].picks.append(pick)
    if people:
        # The first free room in each group is the tightest fit there.
        for group in groups:
            first_free = next((p for p in group.picks if p.state == FREE), None)
            if first_free:
                first_free.best_fit = True

    recent = [Pick(recent_pool[pk], *states[pk]) for pk in recent_ids if pk in recent_pool]

    return {
        "is_vehicle": is_vehicle,
        "kind": kind,
        "slots": slots,
        "date": date,
        "end_date": end_date,
        "from_time": from_time,
        "until_time": until_time,
        "free_only": free_only,
        "q": term,
        "people": people or "",
        "chosen_types": chosen_types,
        "types": [] if is_vehicle else VenueType.objects.filter(is_active=True),
        "problems": problems,
        "groups": groups,
        "count": len(picks),
        "recent": recent,
        # Grid first, as the office asked; a person's own choice of List is
        # remembered by picker.js in their browser.
        "default_view": "grid",
        "preview": GROUP_PREVIEW,
        "booking_query": (
            f"start_date={date:%Y-%m-%d}&start_time={from_time}"
            f"&end_date={end_date:%Y-%m-%d}&end_time={until_time}"
        ),
    }
