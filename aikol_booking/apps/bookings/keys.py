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

from apps.resources.models import ResourceType

from .models import Booking, BookingStatus, KeyHandover, ManagementDecision, Via


@transaction.atomic
def issue_key(
    booking: Booking,
    *,
    issued_by,
    collected_by_name: str = "",
    collected_by_contact: str = "",
    mileage_out: int | None = None,
    via: str = Via.OFFICE,
) -> KeyHandover:
    """Record that the key has been handed over.

    Only for an APPROVED booking. Handing out a key for a request nobody has
    decided yet would make the approval step meaningless.

    `via=KIOSK` is a person recording their own collection on the office PC.
    It is held as awaiting confirmation until the Admin confirms it.
    """
    if booking.status != BookingStatus.APPROVED:
        raise ValidationError(
            f"{booking.booking_reference} is {booking.get_status_display().lower()}. "
            "A key is issued only for an approved booking."
        )
    if not booking.is_fully_approved:
        raise ValidationError(
            "The key can be issued once management has approved the trip and a driver "
            "is assigned."
        )

    handover, _ = KeyHandover.objects.get_or_create(booking=booking)
    if handover.issued_at:
        raise ValidationError(
            f"The key for {booking.booking_reference} was issued on "
            f"{timezone.localtime(handover.issued_at):%d %b %Y at %H:%M}."
        )
    handover.issued_at = timezone.now()
    handover.issued_by = issued_by
    # Blank means the person who booked came for it. The record keeps a name
    # either way: "who has this key" must be answerable from the row alone.
    handover.collected_by_name = collected_by_name.strip() or booking.user.full_name
    handover.collected_by_contact = collected_by_contact.strip()
    handover.mileage_out = mileage_out if booking.is_vehicle else None
    handover.issue_via = via
    _confirm(handover, "issue", issued_by if via == Via.OFFICE else None)
    handover.save()
    return handover


@transaction.atomic
def return_key(
    booking: Booking,
    *,
    returned_to,
    returned_by_name: str,
    condition_notes: str = "",
    mileage_in: int | None = None,
    fuel_receipt=None,
    via: str = Via.OFFICE,
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
    if (
        booking.is_vehicle
        and mileage_in is not None
        and handover.mileage_out is not None
        and mileage_in < handover.mileage_out
    ):
        raise ValidationError(
            f"The mileage on return ({mileage_in} km) is lower than when the key went out "
            f"({handover.mileage_out} km)."
        )

    handover.returned_at = timezone.now()
    handover.returned_to = returned_to
    handover.returned_by_name = returned_by_name.strip()
    handover.condition_notes = condition_notes.strip()
    if booking.is_vehicle:
        handover.mileage_in = mileage_in
        if fuel_receipt:
            handover.fuel_receipt = fuel_receipt
    handover.return_via = via
    _confirm(handover, "return", returned_to if via == Via.OFFICE else None)
    handover.save()
    return handover


def _confirm(handover: KeyHandover, step: str, by) -> None:
    """An office entry is confirmed as it is made; a kiosk entry waits."""
    setattr(handover, f"{step}_confirmed_by", by)
    setattr(handover, f"{step}_confirmed_at", timezone.now() if by else None)


@transaction.atomic
def confirm_key_entry(handover: KeyHandover, step: str, *, confirmed_by) -> KeyHandover:
    """The Admin agrees that a kiosk entry happened: the key really changed hands."""
    locked = KeyHandover.objects.select_for_update().get(pk=handover.pk)
    pending = locked.issue_pending if step == "issue" else locked.return_pending
    if not pending:
        raise ValidationError("There is nothing waiting to be confirmed for this key.")
    _confirm(locked, step, confirmed_by)
    # Whoever confirms a collection is the member of staff who let the key go.
    if step == "issue":
        locked.issued_by = confirmed_by
    else:
        locked.returned_to = confirmed_by
    locked.save()
    return locked


@transaction.atomic
def reject_key_entry(handover: KeyHandover, step: str) -> KeyHandover:
    """Undo a kiosk entry the office says did not happen.

    The handover row stays, cleared back to its earlier state; the audit log
    keeps the record of what was claimed and that it was rejected.
    """
    locked = KeyHandover.objects.select_for_update().get(pk=handover.pk)
    if step == "issue":
        if not locked.issue_pending:
            raise ValidationError("There is no collection waiting to be confirmed.")
        if locked.returned_at:
            raise ValidationError("Deal with the return first; it was recorded after this.")
        locked.issued_at = locked.issued_by = None
        locked.collected_by_name = locked.collected_by_contact = ""
        locked.mileage_out = None
        locked.issue_via = Via.OFFICE
    else:
        if not locked.return_pending:
            raise ValidationError("There is no return waiting to be confirmed.")
        locked.returned_at = locked.returned_to = None
        locked.returned_by_name = locked.condition_notes = ""
        locked.mileage_in = None
        locked.fuel_receipt = None
        locked.return_via = Via.OFFICE
    _confirm(locked, step, None)
    locked.save()
    return locked


def find_by_reference(reference: str) -> Booking | None:
    """The booking a person types at the kiosk or the office searches for."""
    reference = (reference or "").strip().upper()
    if not reference:
        return None
    return (
        Booking.objects.select_related("resource", "user", "key_handover")
        .filter(booking_reference__iexact=reference)
        .first()
    )


def awaiting_confirmation() -> QuerySet[KeyHandover]:
    """Kiosk entries the Admin has not yet confirmed, oldest first."""
    return (
        KeyHandover.objects.filter(
            Q(issued_at__isnull=False, issue_confirmed_at__isnull=True)
            | Q(returned_at__isnull=False, return_confirmed_at__isnull=True)
        )
        .select_related("booking", "booking__resource", "booking__user", "issued_by")
        .order_by("issued_at")
    )


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
        .filter(
            Q(resource__resource_type=ResourceType.VENUE)
            | Q(management_status=ManagementDecision.APPROVED)
        )
        .filter(Q(key_handover__isnull=True) | Q(key_handover__issued_at__isnull=True))
        .select_related("resource", "user")
        .order_by("start_at")
    )
