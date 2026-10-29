"""Resource management rules that are not the booking rules.

Two things live here because they are easy to get subtly wrong in a view:
deleting a resource, and reordering facilities or venues.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Facility, Resource, ResourceStatus, Vehicle, Venue


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


@transaction.atomic
def reorder_resources(model, ordered_ids: list[int]) -> None:
    """Move venues or vehicles into the given order and keep unlisted ones after them.

    The interface only enables this on the complete, unfiltered list, but preserving
    unlisted rows makes a forged or stale filtered request safe as well.
    """
    ordered = list(dict.fromkeys(int(i) for i in ordered_ids))
    known = {row.pk: row for row in model.objects.select_for_update()}
    missing = [pk for pk in ordered if pk not in known]
    if missing:
        raise ValidationError(f"No {model._meta.verbose_name} with id {missing[0]}.")

    rest = [
        row.pk
        for row in model.objects.select_for_update()
        .exclude(pk__in=ordered)
        .order_by("display_order", "name", "pk")
    ]
    for position, pk in enumerate(ordered + rest, start=1):
        known[pk].display_order = position
    model.objects.bulk_update(known.values(), ["display_order"])


def reorder_venues(ordered_ids: list[int]) -> None:
    reorder_resources(Venue, ordered_ids)


def reorder_vehicles(ordered_ids: list[int]) -> None:
    reorder_resources(Vehicle, ordered_ids)


# Venue photographs are shown side by side on cards and in the gallery, so they
# are all one shape. The browser offers a crop before upload; this is the rule
# itself, applied to every venue upload whether or not the crop step ran.
VENUE_PHOTO_SIZE = (1600, 1200)


def fit_venue_photo(upload):
    """Return a 1600 x 1200 JPEG of `upload`, centre-cropped to 4:3.

    Re-encoding also drops the camera's EXIF block, which can carry the
    location a photograph was taken.
    """
    import io

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps

    upload.seek(0)
    with Image.open(upload) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        fitted = ImageOps.fit(image, VENUE_PHOTO_SIZE, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    fitted.save(buffer, format="JPEG", quality=85, optimize=True)
    stem = (upload.name or "photo").rsplit(".", 1)[0]
    return ContentFile(buffer.getvalue(), name=f"{stem}.jpg")
