"""When each booking email goes, and what its fields contain.

The wording itself lives in `wording.py`, where the office can change it from
System, Emails. Two rules apply to every message here, and both are tested:

  - It is addressed to `booking.user`, never to `created_by`. When an
    administrator books on someone's behalf, the person the booking is FOR is
    the one who needs to know.
  - No field carries a matriculation number, a telephone number or a driving
    licence number. Those are personal data, and a confirmation message has no
    use for any of them; an edited wording cannot add them, because the only
    fields it can use are the ones filled in here.
"""

from __future__ import annotations

from django.utils import timezone

from .wording import send


def _when(booking) -> str:
    start = timezone.localtime(booking.start_at)
    end = timezone.localtime(booking.end_at)
    if start.date() == end.date():
        return f"{start:%A, %d %B %Y}, {start:%H:%M} to {end:%H:%M}"
    return f"{start:%a %d %b %Y, %H:%M} to {end:%a %d %b %Y, %H:%M}"


def _details(booking) -> str:
    lines = [
        f"Reference: {booking.booking_reference}",
        f"Resource:  {booking.resource.name}",
        f"When:      {_when(booking)}",
        f"Purpose:   {booking.purpose}",
    ]
    if booking.created_by_id != booking.user_id:
        lines.append("Requested by the Kulliyyah office on your behalf.")
    return "\n".join(lines)


def _booking(booking, **extra) -> dict:
    return {
        "name": booking.user.full_name,
        "reference": booking.booking_reference,
        "resource": booking.resource.name,
        "when": _when(booking),
        "purpose": booking.purpose,
        "details": _details(booking),
        **extra,
    }


def _dates(bookings, *, with_end: bool = True) -> str:
    lines = []
    for b in bookings:
        start = timezone.localtime(b.start_at)
        period = f"{start:%a %d %b %Y, %H:%M}"
        if with_end:
            period += f" to {timezone.localtime(b.end_at):%H:%M}"
        lines.append(f"  {period}  {b.booking_reference}")
    return "\n".join(lines)


def _series(series, bookings, **extra) -> dict:
    return {
        "name": series.user.full_name,
        "resource": series.resource.name,
        "purpose": series.purpose,
        "count": str(len(bookings)),
        **extra,
    }


def booking_submitted(booking) -> None:
    send("BOOKING_SUBMITTED", to=booking.user.email, values=_booking(booking))


def booking_approved(booking) -> None:
    # A car's first approval is not the end of it: management still decides.
    # The outbox kind stays BOOKING_APPROVED for both, so a failure is traced
    # to the same action whichever wording went out.
    key = (
        "BOOKING_APPROVED_VEHICLE"
        if booking.resource.resource_type == "VEHICLE"
        else "BOOKING_APPROVED"
    )
    send(key, to=booking.user.email, values=_booking(booking), kind="BOOKING_APPROVED")


def vehicle_management_decided(booking, *, approved: bool) -> None:
    if approved:
        send(
            "VEHICLE_MANAGEMENT_APPROVED",
            to=booking.user.email,
            values=_booking(booking, driver=booking.driver_name),
        )
    else:
        send(
            "VEHICLE_MANAGEMENT_REJECTED",
            to=booking.user.email,
            values=_booking(booking, reason=booking.management_decision_reason),
        )


def booking_rejected(booking) -> None:
    send(
        "BOOKING_REJECTED",
        to=booking.user.email,
        values=_booking(booking, reason=booking.decision_reason),
    )


def booking_cancelled(booking) -> None:
    send(
        "BOOKING_CANCELLED",
        to=booking.user.email,
        values=_booking(booking, reason=booking.cancellation_reason),
    )


def series_decided(series, bookings: list, *, approved: bool, reason: str = "") -> None:
    """ONE summary message for a series, not one per occurrence.

    A semester of weekly classes is twenty-six occurrences. Twenty-six identical
    emails would be indistinguishable from a fault, and the recipient would stop
    reading all of them.
    """
    send(
        "SERIES_APPROVED" if approved else "SERIES_REJECTED",
        to=series.user.email,
        values=_series(series, bookings, dates=_dates(bookings), reason=reason),
    )


def series_submitted(series, bookings: list, *, skipped: list) -> None:
    """One message for a whole series, listing what was NOT created too.

    Dates left out are the part people need to see. A silent gap in a semester
    is discovered in week seven, by a class standing outside a locked room.
    """
    not_included = ""
    if skipped:
        left_out = "\n".join(
            f"  {occ['date']:%a %d %b %Y}: {occ.get('skip_reason') or 'already reserved'}"
            for occ in skipped
        )
        not_included = f"Not included ({len(skipped)}):\n{left_out}"
    send(
        "SERIES_SUBMITTED",
        to=series.user.email,
        values=_series(series, bookings, dates=_dates(bookings), not_included=not_included),
    )


def series_cancelled(series, bookings: list, *, reason: str) -> None:
    send(
        "SERIES_CANCELLED",
        to=series.user.email,
        values=_series(series, bookings, dates=_dates(bookings, with_end=False), reason=reason),
    )
