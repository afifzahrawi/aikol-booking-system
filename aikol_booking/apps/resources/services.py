"""Resource management rules that are not the booking rules.

Two things live here because they are easy to get subtly wrong in a view:
deleting a resource, and reordering facilities.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Facility, Resource, ResourceStatus


class DeletionRefused(ValidationError):
    """Raised with the gate that stopped it, so the interface can say which."""


def delete_resource(resource: Resource) -> None:
    """Delete a venue or vehicle, through two gates that are different gates.

    The first is a matter of intent: the resource must be deactivated before it
    can be deleted, so nothing leaves the system in one click from a list and
    the room or car spends time visibly out of service first.

    The second is not negotiable. A resource that any booking refers to cannot
    be deleted at all, whatever its status — `Booking.resource` is PROTECT and
    the database refuses. Booking history has to stay complete for the seven-year
    audit retention, and history pointing at a resource the system no longer
    holds is not complete.

    Deletion is therefore for one case: a record entered in error that nobody
    ever booked.
    """
    if resource.status == ResourceStatus.ACTIVE:
        raise DeletionRefused(
            f"{resource.name} must be deactivated before it can be deleted."
        )
    used = resource.bookings.count()
    if used:
        raise DeletionRefused(
            f"{used} booking record{'' if used == 1 else 's'} "
            f"refer{'s' if used == 1 else ''} to {resource.name}, so it cannot be deleted. "
            "It stays deactivated, with its record and its history intact."
        )
    resource.delete()


@transaction.atomic
def reorder_facilities(ordered_ids: list[int]) -> None:
    """Rewrite display_order as 1..n from the given sequence.

    The whole column is rewritten rather than the moved row patched, so there
    are never gaps or ties to reason about afterwards. Any facility missing from
    the list keeps its relative position at the end — a reorder posted from a
    filtered table must not silently renumber the rows it could not see.
    """
    ordered = list(dict.fromkeys(int(i) for i in ordered_ids))
    known = {f.pk: f for f in Facility.objects.all()}
    missing = [pk for pk in ordered if pk not in known]
    if missing:
        raise ValidationError(f"No facility with id {missing[0]}.")

    rest = [f.pk for f in Facility.objects.order_by("display_order", "name") if f.pk not in ordered]
    for position, pk in enumerate(ordered + rest, start=1):
        known[pk].display_order = position
    Facility.objects.bulk_update(known.values(), ["display_order"])
