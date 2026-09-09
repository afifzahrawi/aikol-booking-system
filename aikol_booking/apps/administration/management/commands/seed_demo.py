"""Fill a development database with obviously fictional demonstration data.

Every account uses `@demo.aikol.test`, which cannot receive mail, and every name
is invented. That is a project convention, not a nicety: demonstration data that
looks real ends up quoted in a meeting as though it were a measurement.

Refuses to run with DEBUG off. This creates accounts with known passwords, and
there is no circumstance in which that belongs on a production database.
"""

from __future__ import annotations

import datetime as dt
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.administration.models import SiteContent, SystemSetting
from apps.bookings.models import (
    AcademicTerm,
    Booking,
    BookingStatus,
    DriverArrangement,
    KeyHandover,
    TermBreak,
)
from apps.resources.models import Facility, ResourceImage, ResourceStatus, Vehicle, Venue

PASSWORD = "aikol-demo-2026"

PEOPLE = [
    ("Kulliyyah Office", "office@demo.aikol.test", Role.ADMINISTRATOR, Affiliation.STAFF, "STAFF-1001"),
    ("Deputy Director", "deputy@demo.aikol.test", Role.APPROVER, Affiliation.STAFF, "STAFF-1002"),
    ("Dr Hafiz Rahman", "hafiz@demo.aikol.test", Role.USER, Affiliation.LECTURER, "STAFF-2041"),
    ("Dr Sarah Lim", "sarah@demo.aikol.test", Role.USER, Affiliation.LECTURER, "STAFF-2042"),
    ("Aiman Zulkifli", "aiman@demo.aikol.test", Role.USER, Affiliation.STUDENT, "S1042"),
    ("Nurul Izzati", "nurul@demo.aikol.test", Role.USER, Affiliation.STUDENT, "S1043"),
    ("Chandran Menon", "chandran@demo.aikol.test", Role.USER, Affiliation.STUDENT, "S1044"),
    ("Farah Aziz", "farah@demo.aikol.test", Role.USER, Affiliation.STAFF, "STAFF-3011"),
]

# The trailing slug names the prototype's placeholder drawing, so the seeded
# system looks like the design AIKOL approved rather than like flat colour.
VENUES = [
    ("AIKOL-MC-01", "Moot Court Room", "MOOT_COURT", "Level 2, AIKOL Main Building", "2", 80, "moot-court"),
    ("AIKOL-SR-01", "Seminar Room 1", "SEMINAR", "Level 1, AIKOL Main Building", "1", 45, "seminar-a"),
    ("AIKOL-SR-02", "Seminar Room 2", "SEMINAR", "Level 1, AIKOL Main Building", "1", 40, "seminar-b"),
    ("AIKOL-MR-01", "Meeting Room A", "MEETING", "Level 3, AIKOL Main Building", "3", 16, "meeting-a"),
    ("AIKOL-MR-02", "Meeting Room B", "MEETING", "Level 1, AIKOL Annex", "1", 10, "meeting-b"),
    ("AIKOL-LR-01", "Lecture Room 1", "LECTURE", "Level 2, AIKOL Main Building", "2", 120, "lecture"),
    ("AIKOL-DR-01", "Discussion Room 1", "DISCUSSION", "Level 1, AIKOL Library Wing", "1", 8, "discussion"),
    ("AIKOL-CF-01", "Conference Room", "CONFERENCE", "Level 3, AIKOL Main Building", "3", 60, "conference"),
]

CARS = [
    ("AIKOL-CAR-01", "Kulliyyah Car 1", "WXY 1234", "Proton", "Saga", 2022, 5, "AUTO", "car-saga"),
    ("AIKOL-CAR-02", "Kulliyyah Car 2", "WXY 5678", "Perodua", "Bezza", 2023, 5, "AUTO", "car-bezza"),
    ("AIKOL-CAR-03", "Kulliyyah Van", "WXY 9012", "Toyota", "Innova", 2021, 7, "AUTO", "car-innova"),
    ("AIKOL-CAR-04", "Kulliyyah Car 4", "WXY 3456", "Proton", "Exora", 2020, 7, "MANUAL", "car-exora"),
]

PURPOSES = [
    "Contract Law tutorial", "Moot court practice", "Final year project discussion",
    "Departmental meeting", "Guest lecture: Islamic jurisprudence", "Study group",
    "Postgraduate supervision", "Staff briefing", "Client interview simulation",
]

TRIPS = [
    ("AIKOL, Gombak", "Palace of Justice, Putrajaya", "Court visit with students"),
    ("AIKOL, Gombak", "IIUM Kuantan Campus", "Inter-campus moot competition"),
    ("AIKOL, Gombak", "Bar Council, Kuala Lumpur", "Meeting with the Bar Council"),
]


# Resources carry an `image_slug` naming one of the prototype's placeholder
# drawings, served from static/. Nothing is uploaded, so the rule that
# user-supplied SVG is refused stays exactly as it was.


class Command(BaseCommand):
    help = "Create fictional demonstration data for a development database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Remove existing demonstration records first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "This creates accounts with a known password and will not run with DEBUG off."
            )

        if options["reset"]:
            KeyHandover.objects.all().delete()
            Booking.objects.all().delete()
            ResourceImage.objects.all().delete()
            Venue.objects.all().delete()
            Vehicle.objects.all().delete()
            User.objects.filter(email__endswith="@demo.aikol.test").delete()
            self.stdout.write("Cleared previous demonstration data.")

        SystemSetting.seed()
        content = SiteContent.load()
        content.address = (
            "Kulliyyah Office, Level 1, AIKOL Main Building\n"
            "International Islamic University Malaysia, 53100 Gombak, Selangor"
        )
        content.phone = "03-6196 4000"
        content.email = "booking-aikol@iium.edu.my"
        content.office_hours = "Mon–Fri, 08:30–17:00"
        content.save()

        # -- People ------------------------------------------------------
        people = {}
        for name, email, role, affiliation, number in PEOPLE:
            person, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": name, "role": role, "affiliation": affiliation,
                    "identification_number": number, "phone": "03-6196 4000",
                    "email_verified": True, "is_active": True,
                },
            )
            if created:
                person.set_password(PASSWORD)
                if role == Role.ADMINISTRATOR:
                    person.is_staff = True
                    person.is_superuser = True
                if affiliation in (Affiliation.LECTURER, Affiliation.STAFF):
                    person.licence_number = f"D{number[-6:]}"
                    person.licence_expiry = timezone.localdate() + dt.timedelta(days=500)
                person.save()
            people[email] = person

        # -- Facilities --------------------------------------------------
        from apps.resources.management.commands.seed_facilities import SEEDED

        for order, (code, label, applies) in enumerate(SEEDED, start=1):
            Facility.objects.get_or_create(
                code=code,
                defaults={"name": label, "applies_to": applies,
                          "display_order": order, "is_seeded": True},
            )
        for code, label, applies in [
            ("prayer_space", "Prayer Space", "VENUE"),
            ("gps", "GPS Navigation", "VEHICLE"),
            ("dashcam", "Dashcam", "VEHICLE"),
        ]:
            Facility.objects.get_or_create(
                code=code,
                defaults={"name": label, "applies_to": applies, "display_order": 90},
            )

        venue_facilities = list(
            Facility.objects.filter(applies_to__in=["VENUE", "BOTH"], is_active=True)
        )
        vehicle_facilities = list(
            Facility.objects.filter(applies_to__in=["VEHICLE", "BOTH"], is_active=True)
        )

        rng = random.Random(24)  # fixed, so a re-seed looks the same

        # -- Venues ------------------------------------------------------
        venues = []
        for code, name, kind, location, floor, capacity, slug in VENUES:
            venue, created = Venue.objects.get_or_create(
                code=code,
                defaults={
                    "name": name, "venue_type": kind, "location": location,
                    "floor": floor, "capacity": capacity, "image_slug": slug,
                    "description": (
                        f"{name} at the Ahmad Ibrahim Kulliyyah of Laws. "
                        "Demonstration record; the Kulliyyah office supplies the real details."
                    ),
                },
            )
            if created:
                venue.facilities.set(rng.sample(venue_facilities, k=min(5, len(venue_facilities))))
            venues.append(venue)
        # One out of service, so the maintenance path is visible.
        venues[-1].status = ResourceStatus.MAINTENANCE
        venues[-1].save(update_fields=["status"])

        # -- Vehicles ----------------------------------------------------
        cars = []
        for code, name, registration, make, model, year, seats, transmission, slug in CARS:
            car, created = Vehicle.objects.get_or_create(
                code=code,
                defaults={
                    "name": name, "registration_number": registration, "make": make,
                    "model": model, "year": year, "seats": seats, "image_slug": slug,
                    "transmission": transmission, "fuel_type": "Petrol",
                    "road_tax_expiry": timezone.localdate() + dt.timedelta(days=rng.randint(40, 300)),
                    "description": "Kulliyyah car. Demonstration record.",
                },
            )
            if created:
                car.facilities.set(rng.sample(vehicle_facilities, k=min(3, len(vehicle_facilities))))
            cars.append(car)

        # -- Academic calendar -------------------------------------------
        today = timezone.localdate()
        monday = today - dt.timedelta(days=today.weekday() + 21)
        terms = [
            ("Semester 2, 2025/2026", monday - dt.timedelta(days=34 * 7), 15),
            ("Semester 1, 2026/2027", monday, 15),
            ("Semester 2, 2026/2027", monday + dt.timedelta(days=22 * 7), 15),
        ]
        for name, start, weeks in terms:
            term, created = AcademicTerm.objects.get_or_create(
                name=name,
                defaults={"start_date": start,
                          "end_date": start + dt.timedelta(days=weeks * 7 - 3)},
            )
            if created:
                TermBreak.objects.create(
                    term=term, name="Mid-semester break",
                    start_date=start + dt.timedelta(days=7 * 7),
                    end_date=start + dt.timedelta(days=7 * 7 + 6),
                )

        # -- Bookings ----------------------------------------------------
        # Spread across the past and the future so the reports and the demand
        # heatmap have something to show.
        requesters = [p for e, p in people.items() if p.role == Role.USER]
        office = people["office@demo.aikol.test"]
        bookable = [v for v in venues if v.status == ResourceStatus.ACTIVE]
        made = 0

        for offset in range(-45, 25):
            day = today + dt.timedelta(days=offset)
            if day.weekday() >= 5 and rng.random() > 0.25:
                continue
            for _ in range(rng.randint(0, 3)):
                venue = rng.choice(bookable)
                hour = rng.choice([8, 9, 10, 11, 13, 14, 15, 16, 19, 20])
                length = rng.choice([1, 2, 2, 3])
                if hour + length > 22:
                    continue
                start = timezone.make_aware(dt.datetime.combine(day, dt.time(hour)))
                end = start + dt.timedelta(hours=length)
                from apps.bookings.services import find_conflicts

                if find_conflicts(venue, start, end).exists():
                    continue
                if offset < 0:
                    status = rng.choices(
                        [BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.REJECTED],
                        weights=[8, 1, 1],
                    )[0]
                else:
                    status = rng.choices(
                        [BookingStatus.APPROVED, BookingStatus.PENDING], weights=[3, 2]
                    )[0]
                person = rng.choice(requesters)
                Booking.objects.create(
                    resource=venue, user=person, created_by=person,
                    start_at=start, end_at=end, purpose=rng.choice(PURPOSES),
                    attendees=rng.randint(4, min(40, venue.capacity)),
                    status=status,
                    decided_by=office if status != BookingStatus.PENDING else None,
                    decided_at=start - dt.timedelta(days=2)
                    if status != BookingStatus.PENDING else None,
                    decision_reason="Room not available for that period."
                    if status == BookingStatus.REJECTED else "",
                    cancellation_reason="Class rescheduled."
                    if status == BookingStatus.CANCELLED else "",
                    cancelled_at=start - dt.timedelta(days=4)
                    if status == BookingStatus.CANCELLED else None,
                )
                made += 1

        # A few vehicle trips, including one multi-day and one VMU request.
        drivers = [p for p in requesters if p.may_drive]
        students = [p for p in requesters if not p.may_drive]
        for index, (origin, destination, purpose) in enumerate(TRIPS):
            car = cars[index % len(cars)]
            start_day = today + dt.timedelta(days=6 + index * 4)
            start = timezone.make_aware(dt.datetime.combine(start_day, dt.time(8, 0)))
            end = start + dt.timedelta(days=index, hours=9)
            self_drive = index < 2
            Booking.objects.create(
                resource=car,
                user=(drivers if self_drive else students)[index % 2],
                created_by=(drivers if self_drive else students)[index % 2],
                start_at=start, end_at=end, purpose=purpose,
                driver_arrangement=(
                    DriverArrangement.SELF_DRIVE if self_drive else DriverArrangement.VMU_DRIVER
                ),
                location_from=origin, location_to=destination,
                passengers=rng.randint(2, car.seats),
                status=BookingStatus.APPROVED if index else BookingStatus.PENDING,
            )
            made += 1

        # -- Keys --------------------------------------------------------
        # One out and returned, one still out, one out and overdue.
        approved = list(
            Booking.objects.filter(status__in=[BookingStatus.APPROVED, BookingStatus.COMPLETED])
            .order_by("start_at")
        )
        if len(approved) >= 3:
            returned, outstanding, overdue = approved[-1], approved[-2], approved[0]
            KeyHandover.objects.get_or_create(
                booking=returned,
                defaults={
                    "issued_at": returned.start_at, "issued_by": office,
                    "collected_by_name": "Aiman Zulkifli", "collected_by_contact": "019-222 3344",
                    "returned_at": returned.end_at, "returned_to": office,
                    "returned_by_name": "Nurul Izzati", "condition_notes": "All in order.",
                },
            )
            KeyHandover.objects.get_or_create(
                booking=outstanding,
                defaults={
                    "issued_at": timezone.now() - dt.timedelta(hours=2), "issued_by": office,
                    "collected_by_name": "Chandran Menon",
                },
            )
            KeyHandover.objects.get_or_create(
                booking=overdue,
                defaults={
                    "issued_at": overdue.start_at, "issued_by": office,
                    "collected_by_name": "Farah Aziz",
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {User.objects.count()} accounts, {Venue.objects.count()} venues, "
            f"{Vehicle.objects.count()} vehicles, {Booking.objects.count()} bookings "
            f"({made} created this run)."
        ))
        self.stdout.write("")
        self.stdout.write("Sign in with any of these. Password for all: " + PASSWORD)
        for name, email, role, _affiliation, _number in PEOPLE[:5]:
            self.stdout.write(f"  {email:<32} {role.title():<14} {name}")
