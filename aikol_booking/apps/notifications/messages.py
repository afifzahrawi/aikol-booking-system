"""The wording of every booking email, in one place.

Two rules apply to every body here, and both are tested:

  - It is addressed to `booking.user`, never to `created_by`. When an
    administrator books on someone's behalf, the person the booking is FOR is
    the one who needs to know.
  - It carries no matriculation number, no telephone number and no driving
    licence number. Those are personal data, and a confirmation message has no
    use for any of them.
"""

from __future__ import annotations

from django.utils import timezone

from .services import queue_email


def _when(booking) -> str:
    start = timezone.localtime(booking.start_at)
    end = timezone.localtime(booking.end_at)
    if start.date() == end.date():
        return f"{start:%A, %d %B %Y}, {start:%H:%M} to {end:%H:%M}"
    return f"{start:%a %d %b %Y, %H:%M} to {end:%a %d %b %Y, %H:%M}"


def _greeting(booking) -> str:
    return f"Assalamualaikum {booking.user.full_name},\n\n"


def _details(booking) -> str:
    lines = [
        f"Reference: {booking.booking_reference}",
        f"Resource:  {booking.resource.name}",
        f"When:      {_when(booking)}",
        f"Purpose:   {booking.purpose}",
    ]
    if booking.created_by_id != booking.user_id:
        lines.append(f"Requested by the Kulliyyah office on your behalf.")
    return "\n".join(lines) + "\n"


def booking_submitted(booking) -> None:
    queue_email(
        to=booking.user.email,
        subject=f"Booking request received — {booking.booking_reference}",
        body=(
            _greeting(booking)
            + "Your booking request has been received and is awaiting a decision "
            "by the Kulliyyah office.\n\n"
            + _details(booking)
            + "\nYou will be emailed again once it is decided. The resource is held "
            "for you in the meantime, so nobody else can book the same period.\n"
        ),
        kind="BOOKING_SUBMITTED",
    )


def booking_approved(booking) -> None:
    queue_email(
        to=booking.user.email,
        subject=f"Booking approved — {booking.booking_reference}",
        body=(
            _greeting(booking)
            + "Your booking has been approved.\n\n"
            + _details(booking)
            + "\nCollect the key from the Kulliyyah office. If you can no longer use "
            "the booking, cancel it so that somebody else can.\n"
        ),
        kind="BOOKING_APPROVED",
    )


def booking_rejected(booking) -> None:
    queue_email(
        to=booking.user.email,
        subject=f"Booking not approved — {booking.booking_reference}",
        body=(
            _greeting(booking)
            + "Your booking request was not approved.\n\n"
            + _details(booking)
            + f"\nReason given: {booking.decision_reason}\n"
            "\nYou are welcome to submit another request for a different period.\n"
        ),
        kind="BOOKING_REJECTED",
    )


def booking_cancelled(booking) -> None:
    queue_email(
        to=booking.user.email,
        subject=f"Booking cancelled — {booking.booking_reference}",
        body=(
            _greeting(booking)
            + "This booking has been cancelled.\n\n"
            + _details(booking)
            + f"\nReason given: {booking.cancellation_reason}\n"
            "\nThe period is now free for anyone else to book.\n"
        ),
        kind="BOOKING_CANCELLED",
    )


def series_decided(series, bookings: list, *, approved: bool, reason: str = "") -> None:
    """ONE summary message for a series, not one per occurrence.

    A semester of weekly classes is twenty-six occurrences. Twenty-six identical
    emails would be indistinguishable from a fault, and the recipient would stop
    reading all of them.
    """
    dates = "\n".join(
        f"  {timezone.localtime(b.start_at):%a %d %b %Y, %H:%M}–"
        f"{timezone.localtime(b.end_at):%H:%M}  {b.booking_reference}"
        for b in bookings
    )
    verb = "approved" if approved else "not approved"
    body = (
        f"Assalamualaikum {series.user.full_name},\n\n"
        f"Your recurring booking for {series.resource.name} has been {verb}.\n\n"
        f"Purpose: {series.purpose}\n"
        f"Occurrences: {len(bookings)}\n\n"
        f"{dates}\n"
    )
    if reason:
        body += f"\nReason given: {reason}\n"
    queue_email(
        to=series.user.email,
        subject=f"Recurring booking {verb} — {series.resource.name}",
        body=body,
        kind="SERIES_APPROVED" if approved else "SERIES_REJECTED",
    )


def series_submitted(series, bookings: list, *, skipped: list) -> None:
    """One message for a whole series, listing what was NOT created too.

    Dates left out are the part people need to see. A silent gap in a semester
    is discovered in week seven, by a class standing outside a locked room.
    """
    dates = "\n".join(
        f"  {timezone.localtime(b.start_at):%a %d %b %Y, %H:%M}–"
        f"{timezone.localtime(b.end_at):%H:%M}  {b.booking_reference}"
        for b in bookings
    )
    body = (
        f"Assalamualaikum {series.user.full_name},\n\n"
        f"Your recurring booking request for {series.resource.name} has been received "
        "and is awaiting a decision by the Kulliyyah office.\n\n"
        f"Purpose: {series.purpose}\n"
        f"Occurrences requested: {len(bookings)}\n\n"
        f"{dates}\n"
    )
    if skipped:
        left_out = "\n".join(
            f"  {occ['date']:%a %d %b %Y}  — {occ.get('skip_reason') or 'already reserved'}"
            for occ in skipped
        )
        body += (
            f"\nNot included ({len(skipped)}):\n{left_out}\n"
            "\nThese dates are listed rather than quietly dropped, so you can decide "
            "what to do about them.\n"
        )
    queue_email(
        to=series.user.email,
        subject=f"Recurring booking request received — {series.resource.name}",
        body=body,
        kind="SERIES_SUBMITTED",
    )


def series_cancelled(series, bookings: list, *, reason: str) -> None:
    dates = "\n".join(
        f"  {timezone.localtime(b.start_at):%a %d %b %Y, %H:%M}  {b.booking_reference}"
        for b in bookings
    )
    queue_email(
        to=series.user.email,
        subject=f"Recurring booking cancelled — {series.resource.name}",
        body=(
            f"Assalamualaikum {series.user.full_name},\n\n"
            f"{len(bookings)} future occurrence{'' if len(bookings) == 1 else 's'} of your "
            f"recurring booking for {series.resource.name} "
            f"{'has' if len(bookings) == 1 else 'have'} been cancelled.\n\n"
            f"{dates}\n\n"
            f"Reason given: {reason}\n\n"
            "Occurrences that have already taken place are unaffected.\n"
        ),
        kind="SERIES_CANCELLED",
    )
