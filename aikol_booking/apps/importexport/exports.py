"""CSV export, streamed.

Generated server-side in batches so a large export does not exhaust memory, and
limited to what the requesting person is authorised to see.

Two rules that are tested rather than trusted:

  - Password hashes are never in any export.
  - Personal identifiers — matriculation number, telephone, driving licence —
    appear only in the USER export, whose purpose requires them. A utilisation
    report has no business carrying somebody's phone number.
"""

from __future__ import annotations

import csv
from typing import Iterator

from django.http import StreamingHttpResponse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.resources.models import Facility, Vehicle, Venue

BATCH = 500


class _Echo:
    """A file-like object whose write() returns the line, so csv.writer can feed
    a generator instead of a buffer."""

    def write(self, value):  # noqa: D102
        return value


def _stream(filename: str, header: list[str], rows: Iterator[list]) -> StreamingHttpResponse:
    writer = csv.writer(_Echo())

    def generate():
        yield writer.writerow(header)
        for row in rows:
            yield writer.writerow(row)

    response = StreamingHttpResponse(generate(), content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="{filename}-{stamp}.csv"'
    return response


def _facility_codes(resource) -> str:
    """Emitted in the same pipe-separated form the import accepts, so an export
    can be edited and re-imported without translation."""
    return "|".join(f.code for f in resource.facilities.all())


def export_bookings(queryset) -> StreamingHttpResponse:
    header = [
        "booking_reference", "user_email", "user_name", "resource_code", "resource_name",
        "resource_type", "start_at", "end_at", "status", "purpose", "attendee_count",
        "destination", "passenger_count", "key_issued_at", "key_returned_at",
    ]

    def rows():
        qs = (
            queryset.select_related("resource", "user")
            .prefetch_related("key_handover")
            .order_by("start_at")
        )
        for booking in qs.iterator(chunk_size=BATCH):
            handover = getattr(booking, "key_handover", None)
            yield [
                booking.booking_reference,
                booking.user.email,
                booking.user.full_name,
                booking.resource.code,
                booking.resource.name,
                booking.resource.resource_type,
                timezone.localtime(booking.start_at).strftime("%Y-%m-%d %H:%M"),
                timezone.localtime(booking.end_at).strftime("%Y-%m-%d %H:%M"),
                booking.status,
                booking.purpose,
                booking.attendees or "",
                booking.location_to or "",
                booking.passengers or "",
                timezone.localtime(handover.issued_at).strftime("%Y-%m-%d %H:%M")
                if handover and handover.issued_at else "",
                timezone.localtime(handover.returned_at).strftime("%Y-%m-%d %H:%M")
                if handover and handover.returned_at else "",
            ]

    return _stream("aikol-bookings", header, rows())


def export_users() -> StreamingHttpResponse:
    """The one export whose purpose requires personal identifiers.

    No password column of any kind — not the hash, not a placeholder. A hash is
    an offline-cracking target and has no legitimate place in a spreadsheet.
    """
    header = [
        "name", "email", "identification_number", "phone", "affiliation", "role", "status",
        "email_verified", "date_joined",
    ]

    def rows():
        for person in User.objects.order_by("full_name").iterator(chunk_size=BATCH):
            yield [
                person.full_name,
                person.email,
                person.identification_number or "",
                person.phone,
                person.get_affiliation_display(),
                person.get_role_display(),
                "Active" if person.is_active else "Inactive",
                "Yes" if person.email_verified else "No",
                timezone.localtime(person.date_joined).strftime("%Y-%m-%d"),
            ]

    return _stream("aikol-users", header, rows())


def export_venues() -> StreamingHttpResponse:
    header = [
        "code", "name", "building", "floor", "venue_type", "capacity", "facilities",
        "bookable_window_start", "bookable_window_end", "status",
    ]

    def rows():
        for venue in Venue.objects.prefetch_related("facilities").order_by("name"):
            yield [
                venue.code, venue.name, venue.location, venue.floor,
                venue.get_venue_type_display(), venue.capacity, _facility_codes(venue),
                venue.opens_at.strftime("%H:%M"), venue.closes_at.strftime("%H:%M"),
                "Active" if venue.status == "ACTIVE" else "Inactive",
            ]

    return _stream("aikol-venues", header, rows())


def export_vehicles() -> StreamingHttpResponse:
    header = [
        "code", "name", "registration_number", "vehicle_class", "make", "model", "year",
        "seats", "transmission", "fuel_type", "facilities", "road_tax_expiry", "status",
    ]

    def rows():
        for car in Vehicle.objects.prefetch_related("facilities").order_by("name"):
            yield [
                car.code, car.name, car.registration_number, "Car", car.make, car.model,
                car.year, car.seats, car.get_transmission_display(), car.fuel_type,
                _facility_codes(car), car.road_tax_expiry.isoformat(),
                "Active" if car.status == "ACTIVE" else "Inactive",
            ]

    return _stream("aikol-vehicles", header, rows())


def export_facilities() -> StreamingHttpResponse:
    header = ["code", "name", "applies_to", "status"]

    def rows():
        for facility in Facility.objects.order_by("display_order", "name"):
            yield [
                facility.code, facility.name, facility.get_applies_to_display(),
                "Active" if facility.is_active else "Inactive",
            ]

    return _stream("aikol-facilities", header, rows())
