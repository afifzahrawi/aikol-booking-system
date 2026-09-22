"""Four resources for the Kulliyyah office to edit into its real ones.

An empty system gives the office nothing to practise on and nothing to copy
the shape of. These four are deliberately ordinary: three venues covering the
kinds most often booked, and one car. They carry no photograph, so each shows
the prototype's own drawing until a real one is uploaded (decision 26).

Idempotent, and it never overwrites: a record whose code already exists is
left exactly as the office has edited it. Safe to run again after a release.

Nothing here is a measurement. The capacities, locations and the registration
number are plainly marked as examples in the description, so nobody mistakes
them for the Kulliyyah's own list.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.resources.models import Facility, ResourceFacility, Vehicle, Venue

EXAMPLE_NOTE = (
    "Example record created at installation. Edit the details, or deactivate it "
    "once the Kulliyyah's own resources are entered."
)

VENUES = [
    {
        "code": "AIKOL-MC-01",
        "name": "Moot Court Room",
        "venue_type": Venue.VenueType.MOOT_COURT,
        "location": "AIKOL Main Building",
        "floor": "Level 1",
        "capacity": 80,
        "facilities": ["projector", "microphone", "sound", "aircond", "internet"],
    },
    {
        "code": "AIKOL-SR-01",
        "name": "Seminar Room 1",
        "venue_type": Venue.VenueType.SEMINAR,
        "location": "AIKOL Main Building",
        "floor": "Level 2",
        "capacity": 40,
        "facilities": ["projector", "whiteboard", "aircond", "internet"],
    },
    {
        "code": "AIKOL-MR-01",
        "name": "Meeting Room A",
        "venue_type": Venue.VenueType.MEETING,
        "location": "AIKOL Main Building",
        "floor": "Level 3",
        "capacity": 16,
        "facilities": ["smart_tv", "whiteboard", "aircond", "video_conf"],
    },
]

VEHICLE = {
    "code": "AIKOL-CAR-01",
    "name": "Kulliyyah Car 1",
    "registration_number": "WXX 0001",
    "make": "Proton",
    "model": "Saga",
    "year": 2023,
    "seats": 5,
    "transmission": Vehicle.Transmission.AUTOMATIC,
    "fuel_type": "Petrol",
    "facilities": ["aircond", "internet"],
}


class Command(BaseCommand):
    help = "Create four example resources (three venues, one car) if they are missing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--road-tax-months",
            type=int,
            default=12,
            help="How far ahead the example car's road tax expiry is set. Default 12 months.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        facilities = {f.code: f for f in Facility.objects.all()}
        created = 0

        for row in VENUES:
            wanted = dict(row)
            codes = wanted.pop("facilities")
            venue, made = Venue.objects.get_or_create(
                code=wanted["code"],
                defaults={**wanted, "description": EXAMPLE_NOTE},
            )
            if made:
                created += 1
                self._attach(venue, codes, facilities)
                self.stdout.write(f"Created venue {venue.code}: {venue.name}.")
            else:
                self.stdout.write(f"{venue.code} already exists; left as it is.")

        wanted = dict(VEHICLE)
        codes = wanted.pop("facilities")
        expiry = timezone.localdate() + dt.timedelta(days=30 * options["road_tax_months"])
        car, made = Vehicle.objects.get_or_create(
            code=wanted["code"],
            defaults={**wanted, "description": EXAMPLE_NOTE, "road_tax_expiry": expiry},
        )
        if made:
            created += 1
            self._attach(car, codes, facilities)
            self.stdout.write(f"Created vehicle {car.code}: {car.name}.")
        else:
            self.stdout.write(f"{car.code} already exists; left as it is.")

        self.stdout.write(
            f"{created} example resource(s) created. "
            "They carry no photograph, so each shows a drawing until one is uploaded."
        )

    def _attach(self, resource, codes, facilities):
        for code in codes:
            facility = facilities.get(code)
            if facility:
                ResourceFacility.objects.get_or_create(resource=resource, facility=facility)
