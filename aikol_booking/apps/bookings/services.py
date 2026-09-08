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
    notify: bool = True,
    **extra,
) -> Booking:
    """Create one booking, re-checking the slot under a row lock.

    Raises ValidationError listing every conflict rather than raising on the
    first, so the requester is told the whole story at once.

    `notify=False` is for occurrences of a series, which are reported by one
    summary message instead of twenty-six identical ones.
    """
    from apps.notifications import messages
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
    booking = Booking.objects.create(
        resource=resource,
        user=user,
        created_by=created_by,
        start_at=start_at,
        end_at=end_at,
        purpose=purpose,
        status=BookingStatus.PENDING,  # every resource requires approval (decision 4)
        **extra,
    )
    if notify:
        # Written in this transaction, so a rollback takes the message with it.
        # The system never tells somebody about a booking that does not exist.
        messages.booking_submitted(booking)
    return booking


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


# ---------------------------------------------------------------------------
# Workflow: approval, rejection, cancellation, and recurring series.
#
# Each of these queues its email INSIDE the same transaction as the change it
# reports. If the transaction rolls back the outbox row goes with it, so the
# system never tells somebody about a booking that does not exist.
# ---------------------------------------------------------------------------


@transaction.atomic
def approve_booking(booking, *, decided_by, reason: str = ""):
    """Approve, re-checking the slot first.

    A PENDING booking already holds its slot, so two overlapping pending
    requests cannot arise through `create_booking`. The re-check is not
    therefore redundant: it is what catches a row that reached the table by some
    other path — a bulk CSV import, an administrator amending a booking's times,
    a shell session, or a future feature nobody has written yet.

    The requirement is that such a request must FAIL here rather than overwrite
    an approved booking. Approval is the last moment before a resource is
    promised to somebody, so it is the right place to look again.
    """
    from apps.notifications import messages

    locked = Booking.objects.select_for_update().get(pk=booking.pk)
    if locked.status != BookingStatus.PENDING:
        raise ValidationError(
            f"{locked.booking_reference} is already "
            f"{locked.get_status_display().lower()} and cannot be approved."
        )
    clashes = find_conflicts(
        locked.resource_id,
        locked.start_at,
        locked.end_at,
        exclude_pk=locked.pk,
        for_update=True,
    ).filter(status=BookingStatus.APPROVED)
    if clashes.exists():
        raise ValidationError(
            "That period has been approved for another booking since this request was "
            "made. Reject this one, or ask the requester for another time."
        )

    locked.status = BookingStatus.APPROVED
    locked.decided_by = decided_by
    locked.decided_at = timezone.now()
    locked.decision_reason = reason
    locked.save(update_fields=["status", "decided_by", "decided_at", "decision_reason"])
    # An occurrence of a series is reported in the series summary instead, so a
    # semester does not produce twenty-six identical messages.
    if locked.series_id is None:
        messages.booking_approved(locked)
    return locked


@transaction.atomic
def reject_booking(booking, *, decided_by, reason: str):
    from apps.notifications import messages

    if not reason.strip():
        raise ValidationError("Give a reason. The requester is told what it is.")
    if booking.status != BookingStatus.PENDING:
        raise ValidationError(
            f"{booking.booking_reference} is already {booking.get_status_display().lower()}."
        )
    booking.status = BookingStatus.REJECTED
    booking.decided_by = decided_by
    booking.decided_at = timezone.now()
    booking.decision_reason = reason
    booking.save(update_fields=["status", "decided_by", "decided_at", "decision_reason"])
    if booking.series_id is None:
        messages.booking_rejected(booking)
    return booking


@transaction.atomic
def cancel_booking(booking, *, cancelled_by, reason: str):
    """Cancel one booking. Sets a status; it never deletes the row.

    The cutoff is checked here rather than only in the view, because a
    cancellation can also arrive from a management command or the shell.
    """
    from apps.notifications import messages

    if not reason.strip():
        raise ValidationError("A reason is required (confirmed follow-up decision).")
    if not booking.can_be_cancelled_by(cancelled_by):
        hours = SystemSetting.get_int("cancellation_cutoff_hours")
        raise ValidationError(
            f"This booking can no longer be cancelled. A user must give {hours // 24} "
            "days' notice; ask the Kulliyyah office."
        )
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.cancellation_reason = reason
    booking.save(update_fields=["status", "cancelled_at", "cancellation_reason"])
    messages.booking_cancelled(booking)
    return booking


@transaction.atomic
def cancel_series(series, *, cancelled_by, reason: str) -> int:
    """Cancel every FUTURE occurrence. Past ones are history and stay put."""
    from apps.notifications import messages

    if not reason.strip():
        raise ValidationError("A reason is required.")
    affected = list(
        series.bookings.filter(status__in=BLOCKING_STATUSES, start_at__gt=timezone.now())
    )
    if not affected:
        return 0
    Booking.objects.filter(pk__in=[b.pk for b in affected]).update(
        status=BookingStatus.CANCELLED,
        cancelled_at=timezone.now(),
        cancellation_reason=reason,
    )
    messages.series_cancelled(series, affected, reason=reason)
    return len(affected)


def plan_series(*, resource, term, weekday_times: dict, starts_on, repeat_until) -> dict:
    """Work out what a series WOULD create, without creating anything.

    Returns three separate lists, because they are three different outcomes and
    the requester has to be able to tell them apart:

      - `bookable` — free teaching dates;
      - `outside`  — dates the calendar excludes, which is the calendar working
                     as intended;
      - `clashing` — dates somebody else already holds, which is not.

    A clash is REPORTED, never silently skipped. Losing week 7 without saying so
    is how a lecturer discovers in October that their class has no room.
    """
    if repeat_until < starts_on:
        raise ValidationError("The series ends before it starts.")

    occurrences = expand_series(
        term=term,
        weekday_times=weekday_times,
        starts_on=starts_on,
        repeat_until=repeat_until,
    )
    bookable, outside, clashing = [], [], []
    for occ in occurrences:
        if occ["skip_reason"]:
            outside.append(occ)
            continue
        start = timezone.make_aware(dt.datetime.combine(occ["date"], occ["start_time"]))
        end = timezone.make_aware(dt.datetime.combine(occ["date"], occ["end_time"]))
        occ = dict(occ, start_at=start, end_at=end)
        (clashing if find_conflicts(resource, start, end).exists() else bookable).append(occ)
    return {"bookable": bookable, "outside": outside, "clashing": clashing}


@transaction.atomic
def create_series(
    *,
    resource,
    user,
    created_by,
    term,
    weekday_times: dict,
    starts_on,
    repeat_until,
    purpose: str,
    accept_partial: bool = False,
):
    """Create the series and every bookable occurrence, or create nothing.

    Atomic on purpose. A failure partway through must leave NO occurrences
    rather than half a semester: half a timetable is worse than none, because it
    looks complete.

    A clash refuses the whole request unless `accept_partial` is set — which the
    interface only sets after showing the requester exactly which dates would be
    dropped and asking. Never decide that for them.
    """
    from apps.bookings.models import BookingSeries
    from apps.notifications import messages

    plan = plan_series(
        resource=resource,
        term=term,
        weekday_times=weekday_times,
        starts_on=starts_on,
        repeat_until=repeat_until,
    )
    if plan["clashing"] and not accept_partial:
        raise ValidationError(
            [
                f"{occ['date']:%a %d %b %Y} {occ['start_time']:%H:%M}–"
                f"{occ['end_time']:%H:%M} is already reserved."
                for occ in plan["clashing"]
            ]
        )
    if not plan["bookable"]:
        raise ValidationError(
            "No date in that range is both inside teaching and free. Check the start "
            "date and the repeat-until date against the semester."
        )

    cap = SystemSetting.get_int("maximum_series_occurrences")
    if len(plan["bookable"]) > cap:
        raise ValidationError(f"A single request may not create more than {cap} bookings.")

    series = BookingSeries.objects.create(
        resource=resource,
        user=user,
        term=term,
        weekday_times=weekday_times,
        starts_on=starts_on,
        repeat_until=repeat_until,
        purpose=purpose,
    )
    created = [
        create_booking(
            resource=resource,
            user=user,
            created_by=created_by,
            start_at=occ["start_at"],
            end_at=occ["end_at"],
            purpose=purpose,
            series=series,
            notify=False,
        )
        for occ in plan["bookable"]
    ]
    # One summary message for the whole series, not one per occurrence.
    messages.series_submitted(series, created, skipped=plan["clashing"] + plan["outside"])
    return series, created, plan


@transaction.atomic
def approve_series(series, *, decided_by, reason: str = ""):
    """Approve every pending occurrence, re-checking each one.

    Each occurrence is re-checked individually because each is a real row that
    could have been overtaken separately. One summary email goes out afterwards.
    """
    from apps.notifications import messages

    approved, refused = [], []
    for booking in series.bookings.filter(status=BookingStatus.PENDING).order_by("start_at"):
        try:
            approved.append(approve_booking(booking, decided_by=decided_by, reason=reason))
        except ValidationError as exc:
            refused.append((booking, "; ".join(exc.messages)))
    if approved:
        messages.series_decided(series, approved, approved=True, reason=reason)
    return approved, refused
