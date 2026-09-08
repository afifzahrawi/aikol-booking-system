"""Key issue and return (decision 17).

Four people can be involved and they are frequently not the same person:

  - who booked the room,
  - who walked into the office and collected the key,
  - which member of staff handed it over,
  - who brought it back, and to whom.

The booking already records the first. The rest are recorded here, because "the
user who booked it" is not who turned up at the counter, and a custody record
that assumes they are the same person is not a custody record.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import Booking, BookingStatus, KeyHandover


@transaction.atomic
def issue_key(
    booking: Booking,
    *,
    issued_by,
    collected_by_name: str,
    collected_by_contact: str = "",
) -> KeyHandover:
    """Record that the key has been handed over.

    Only for an APPROVED booking. Handing out a key for a request nobody has
    decided yet would make the approval step meaningless.
    """
    if booking.status != BookingStatus.APPROVED:
        raise ValidationError(
            f"{booking.booking_reference} is {booking.get_status_display().lower()}. "
            "A key is issued only for an approved booking."
        )
    if not collected_by_name.strip():
        raise ValidationError(
            "Record who is collecting the key. It is often not the person who booked."
        )

    handover, _ = KeyHandover.objects.get_or_create(booking=booking)
    if handover.issued_at:
        raise ValidationError(
            f"The key for {booking.booking_reference} was issued on "
            f"{timezone.localtime(handover.issued_at):%d %b %Y at %H:%M}."
        )
    handover.issued_at = timezone.now()
    handover.issued_by = issued_by
    handover.collected_by_name = collected_by_name.strip()
    handover.collected_by_contact = collected_by_contact.strip()
    handover.save()
    return handover


@transaction.atomic
def return_key(
    booking: Booking,
    *,
    returned_to,
    returned_by_name: str,
    condition_notes: str = "",
) -> KeyHandover:
    """Record that the key has come back.

    Deliberately independent of the booking's status. A booking reaches
    COMPLETED when its end time passes; whether the key came back is a separate
    fact, and conflating them would let the system quietly forget an outstanding
    key the moment the booking's period ended.
    """
    handover = KeyHandover.objects.filter(booking=booking).first()
    if handover is None or not handover.issued_at:
        raise ValidationError(
            f"No key was issued for {booking.booking_reference}, so none can be returned."
        )
    if handover.returned_at:
        raise ValidationError(
            f"The key was already returned on "
            f"{timezone.localtime(handover.returned_at):%d %b %Y at %H:%M}."
        )
    if not returned_by_name.strip():
        raise ValidationError("Record who returned the key.")

    handover.returned_at = timezone.now()
    handover.returned_to = returned_to
    handover.returned_by_name = returned_by_name.strip()
    handover.condition_notes = condition_notes.strip()
    handover.save()
    return handover


def outstanding_keys() -> QuerySet[KeyHandover]:
    """Keys issued and not yet back, worst first.

    Includes COMPLETED bookings on purpose. A booking whose period has ended is
    exactly the case worth chasing — the key is overdue, not resolved.
    """
    return (
        KeyHandover.objects.filter(issued_at__isnull=False, returned_at__isnull=True)
        .select_related("booking", "booking__resource", "booking__user", "issued_by")
        .order_by("booking__end_at")
    )


def keys_awaiting_collection() -> QuerySet[Booking]:
    """Approved bookings, still to come, whose key has not been picked up."""
    return (
        Booking.objects.filter(status=BookingStatus.APPROVED, end_at__gte=timezone.now())
        .filter(Q(key_handover__isnull=True) | Q(key_handover__issued_at__isnull=True))
        .select_related("resource", "user")
        .order_by("start_at")
    )
