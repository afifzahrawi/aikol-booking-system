"""Conflict detection and booking creation.

The rule is implemented ONCE, here, for venues and vehicles alike. Everything
else in the system asks this module rather than reimplementing the comparison.

It is enforced in three places, and the redundancy is the point:

  - the browser, as a convenience, and never trusted;
  - the server, on submission AND again on approval, inside transaction.atomic()
    with select_for_update();
  - the database, by an exclusion constraint, which is what actually makes the
    guarantee true under concurrency.
"""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.administration.models import SystemSetting
from apps.resources.models import Resource, ResourceType, Vehicle

from .models import BLOCKING_STATUSES, Booking, BookingStatus


def find_conflicts(
    resource: Resource | int,
    start_at: dt.datetime,
    end_at: dt.datetime,
    *,
    exclude_pk: int | None = None,
    for_update: bool = False,
) -> QuerySet[Booking]:
    """Bookings that overlap [start_at, end_at) for this resource.

        new_start < existing_end  AND  new_end > existing_start

    Strict comparisons, so 10:00-12:00 and 12:00-14:00 do not conflict. Only
    PENDING and APPROVED bookings are counted — a rejected or cancelled booking
    reserves nothing.
    """
    resource_id = resource.pk if isinstance(resource, Resource) else resource
    qs = Booking.objects.filter(
        resource_id=resource_id,
        status__in=BLOCKING_STATUSES,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if for_update:
        # Locks the overlapping rows so a concurrent request cannot slip a
        # booking in between the check and the insert.
        qs = qs.select_for_update()
    return qs


def validate_period(
    resource: Resource,
    start_at: dt.datetime,
    end_at: dt.datetime,
    *,
    now: dt.datetime | None = None,
) -> list[str]:
    """Every rule about the period itself, independent of who is asking.

    Returns the problems as sentences. An empty list means the period is
    acceptable; it says nothing about whether the slot is free.
    """
    now = now or timezone.now()
    problems: list[str] = []

    if end_at <= start_at:
        problems.append("A booking must end after it starts.")
        return problems

    if start_at < now:
        problems.append("A booking cannot start in the past.")

    limit_days = SystemSetting.get_int("advance_booking_limit_days")
    if start_at.date() > (now + dt.timedelta(days=limit_days)).date():
        problems.append(
            f"Bookings may be made up to {limit_days} days ahead. "
            f"The latest bookable date is {(now + dt.timedelta(days=limit_days)):%d %b %Y}."
        )

    window_start = _parse_time(SystemSetting.get("bookable_window_start"))
    window_end = _parse_time(SystemSetting.get("bookable_window_end"))
    local_start = timezone.localtime(start_at)
    local_end = timezone.localtime(end_at)

    if resource.resource_type == ResourceType.VENUE:
        # A room is occupied inside a single day. Its whole booking must sit in
        # the bookable window, and the nine-hour cap applies.
        if local_start.date() != local_end.date():
            problems.append("A room booking must start and finish on the same day.")
        if local_start.time() < window_start or local_end.time() > window_end:
            problems.append(
                f"Rooms are bookable between {window_start:%H:%M} and {window_end:%H:%M}."
            )
        max_minutes = SystemSetting.get_int("maximum_booking_minutes")
        minutes = (end_at - start_at).total_seconds() / 60
        if minutes > max_minutes:
            hours = max_minutes // 60
            problems.append(
                f"A single booking may not exceed {hours} hours. "
                "A longer occupation needs a second booking."
            )
    else:
        # A car can be out overnight, so the window applies to collection and
        # return rather than to the whole period.
        if local_start.time() < window_start or local_start.time() > window_end:
            problems.append(
                f"A vehicle is collected between {window_start:%H:%M} and {window_end:%H:%M}."
            )
        if local_end.time() < window_start or local_end.time() > window_end:
            problems.append(
                f"A vehicle is returned between {window_start:%H:%M} and {window_end:%H:%M}."
            )
        max_days = SystemSetting.get_int("maximum_vehicle_trip_days")
        days = (local_end.date() - local_start.date()).days + 1
        if days > max_days:
            problems.append(f"A trip may not exceed {max_days} days.")

    if not resource.is_bookable:
        # For an untaxed car this is deliberately silent about the reason. You
        # cannot lawfully drive an untaxed vehicle, but the expiry date is an
        # office matter and appears only on administrator screens.
        problems.append(f"{resource.name} is not available for that period.")

    return problems


def check_driver_arrangement(user, resource: Resource, arrangement: str) -> list[str]:
    """Who may book is not who may drive.

    Anyone may request a car. A student may never drive a Kulliyyah car, so a
    student's booking must request a VMU driver. A self-drive booking needs a
    licence on file that is still valid at the END of the trip.
    """
    from .models import DriverArrangement

    if not isinstance(resource, Vehicle) and resource.resource_type != ResourceType.VEHICLE:
        return []
    problems: list[str] = []
    if arrangement == DriverArrangement.SELF_DRIVE:
        if not user.may_drive:
            problems.append(
                "Only lecturers and staff may drive a Kulliyyah car. "
                "Request a driver from the Vehicle Management Unit instead."
            )
        if not user.licence_number or not user.licence_expiry:
            problems.append("A driving licence number and expiry date are required to self-drive.")
    elif arrangement == DriverArrangement.VMU_DRIVER:
        problems.append(
            "A Vehicle Management Unit driver is requested through STADD and needs Kulliyyah "
            "management approval to use a Kulliyyah car — a second approval on top of this booking."
        )
    return problems


@transaction.atomic
def create_booking(
    *,
    resource: Resource,
    user,
    created_by,
    start_at: dt.datetime,
    end_at: dt.datetime,
    purpose: str,
    **extra,
) -> Booking:
    """Create one booking, re-checking the slot under a row lock.

    Raises ValidationError listing every conflict rather than raising on the
    first, so the requester is told the whole story at once.
    """
    clashes = list(
        find_conflicts(resource, start_at, end_at, for_update=True).select_related("resource")
    )
    if clashes:
        raise ValidationError(
            [
                f"Already reserved: {timezone.localtime(c.start_at):%d %b %Y, %H:%M}"
                f"–{timezone.localtime(c.end_at):%H:%M} ({c.get_status_display().lower()})."
                for c in clashes
            ]
        )
    return Booking.objects.create(
        resource=resource,
        user=user,
        created_by=created_by,
        start_at=start_at,
        end_at=end_at,
        purpose=purpose,
        status=BookingStatus.PENDING,  # every resource requires approval (decision 4)
        **extra,
    )


def expand_series(
    *,
    term,
    weekday_times: dict,
    starts_on: dt.date,
    repeat_until: dt.date,
) -> list[dict]:
    """Turn a recurrence definition into candidate occurrences.

    Every candidate is returned, including the ones that fall outside teaching,
    each carrying the reason it would be left out. Nothing is silently dropped:
    an occurrence outside teaching is the calendar working as intended, and a
    clash is somebody already being there. They are different outcomes and the
    caller has to be able to tell them apart.
    """
    cap = SystemSetting.get_int("maximum_series_occurrences")
    out: list[dict] = []
    day = starts_on
    while day <= repeat_until and len(out) < cap:
        times = weekday_times.get(str(day.weekday()))
        if times:
            out.append(
                {
                    "date": day,
                    "start_time": _parse_time(times[0]),
                    "end_time": _parse_time(times[1]),
                    "skip_reason": term.exclusion_for(day) if term else "",
                }
            )
        day += dt.timedelta(days=1)
    return out


def _parse_time(value: str) -> dt.time:
    hour, minute = value.split(":")
    return dt.time(int(hour), int(minute))
