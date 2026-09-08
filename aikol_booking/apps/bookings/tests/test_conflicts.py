"""The conflict table from docs/technical/testing-strategy.md.

The whole table runs twice — once against a venue, once against a vehicle —
because the rule is shared and the results must be identical. If they ever
diverge, something has grown a resource-specific code path that should not
exist. The fixture is parameterised rather than the tests copied.
"""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Affiliation, User
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.services import create_booking, find_conflicts
from apps.resources.models import Vehicle, Venue


def at(day: dt.date, hhmm: str) -> dt.datetime:
    hour, minute = (int(p) for p in hhmm.split(":"))
    naive = dt.datetime.combine(day, dt.time(hour, minute))
    return timezone.make_aware(naive)


class ConflictRuleMixin:
    """One table of cases, applied to whichever resource the subclass builds."""

    def make_resource(self, code: str):  # pragma: no cover - overridden
        raise NotImplementedError

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="requester@demo.aikol.test",
            password="prototype-password-1",
            full_name="Test Requester",
            phone="03-6196 4000",
            affiliation=Affiliation.LECTURER,
            email_verified=True,
        )
        self.resource = self.make_resource("R-01")
        self.other_resource = self.make_resource("R-02")
        # A fixed future Wednesday, so no test depends on the day it runs.
        self.day = timezone.localdate() + dt.timedelta(days=14)
        self.other_day = self.day + dt.timedelta(days=1)
        self.existing = self.book("10:00", "12:00")

    def book(self, start: str, end: str, *, status=BookingStatus.APPROVED, resource=None, day=None):
        booking = Booking.objects.create(
            resource=resource or self.resource,
            user=self.user,
            created_by=self.user,
            start_at=at(day or self.day, start),
            end_at=at(day or self.day, end),
            purpose="Fixture",
            status=status,
        )
        return booking

    def conflicts(self, start: str, end: str, *, resource=None, day=None) -> int:
        return find_conflicts(
            resource or self.resource, at(day or self.day, start), at(day or self.day, end)
        ).count()

    # -- The table -------------------------------------------------------

    def test_identical_period_is_rejected(self):
        self.assertEqual(self.conflicts("10:00", "12:00"), 1)

    def test_partial_overlap_late_is_rejected(self):
        self.assertEqual(self.conflicts("11:00", "13:00"), 1)

    def test_partial_overlap_early_is_rejected(self):
        self.assertEqual(self.conflicts("09:00", "11:00"), 1)

    def test_inside_existing_is_rejected(self):
        self.assertEqual(self.conflicts("10:30", "11:00"), 1)

    def test_surrounding_existing_is_rejected(self):
        self.assertEqual(self.conflicts("09:00", "13:00"), 1)

    def test_adjacent_before_is_accepted(self):
        """08:00-10:00 touches but does not overlap. The comparison is strict."""
        self.assertEqual(self.conflicts("08:00", "10:00"), 0)

    def test_adjacent_after_is_accepted(self):
        self.assertEqual(self.conflicts("12:00", "14:00"), 0)

    def test_different_resource_same_time_is_accepted(self):
        self.assertEqual(self.conflicts("10:00", "12:00", resource=self.other_resource), 0)

    def test_different_date_same_time_is_accepted(self):
        self.assertEqual(self.conflicts("10:00", "12:00", day=self.other_day), 0)

    def test_rejected_booking_does_not_reserve(self):
        self.existing.status = BookingStatus.REJECTED
        self.existing.save(update_fields=["status"])
        self.assertEqual(self.conflicts("10:00", "12:00"), 0)

    def test_cancelled_booking_does_not_reserve(self):
        self.existing.status = BookingStatus.CANCELLED
        self.existing.save(update_fields=["status"])
        self.assertEqual(self.conflicts("10:00", "12:00"), 0)

    def test_pending_booking_does_reserve(self):
        """A request awaiting a decision holds the slot. Otherwise two people
        could each be told to wait for the same room."""
        self.existing.status = BookingStatus.PENDING
        self.existing.save(update_fields=["status"])
        self.assertEqual(self.conflicts("10:00", "12:00"), 1)

    # -- The service refuses, not just the query -------------------------

    def test_create_booking_refuses_a_clash(self):
        with self.assertRaises(ValidationError):
            create_booking(
                resource=self.resource,
                user=self.user,
                created_by=self.user,
                start_at=at(self.day, "11:00"),
                end_at=at(self.day, "13:00"),
                purpose="Should not be created",
            )
        self.assertEqual(Booking.objects.filter(resource=self.resource).count(), 1)

    def test_create_booking_accepts_an_adjacent_slot(self):
        booking = create_booking(
            resource=self.resource,
            user=self.user,
            created_by=self.user,
            start_at=at(self.day, "12:00"),
            end_at=at(self.day, "14:00"),
            purpose="Adjacent",
        )
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertTrue(booking.booking_reference.startswith("BK-"))


class VenueConflictTests(ConflictRuleMixin, TestCase):
    def make_resource(self, code: str) -> Venue:
        return Venue.objects.create(
            code=f"VEN-{code}",
            name=f"Seminar Room {code}",
            venue_type=Venue.VenueType.SEMINAR,
            location="Level 1",
            capacity=30,
        )


class VehicleConflictTests(ConflictRuleMixin, TestCase):
    def make_resource(self, code: str) -> Vehicle:
        return Vehicle.objects.create(
            code=f"CAR-{code}",
            name=f"Kulliyyah Car {code}",
            registration_number=f"WXX {code}",
            make="Proton",
            model="Saga",
            year=2022,
            seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=365),
        )


class MultiDayOverlapTests(TestCase):
    """A trip that runs overnight. This is what the timestamp columns bought:
    the old date-plus-two-times design could not express it at all."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="driver@demo.aikol.test",
            password="prototype-password-1",
            full_name="Test Driver",
            phone="03-6196 4000",
            affiliation=Affiliation.STAFF,
            email_verified=True,
        )
        self.car = Vehicle.objects.create(
            code="CAR-MD",
            name="Kulliyyah Car",
            registration_number="WMD 1234",
            make="Toyota",
            model="Innova",
            year=2021,
            seats=7,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=365),
        )
        # Anchor on a real Monday two weeks out.
        today = timezone.localdate()
        self.monday = today + dt.timedelta(days=(7 - today.weekday()) + 7)
        self.sunday = self.monday - dt.timedelta(days=1)
        self.tuesday = self.monday + dt.timedelta(days=1)
        self.wednesday = self.monday + dt.timedelta(days=2)
        self.thursday = self.monday + dt.timedelta(days=3)
        self.friday = self.monday + dt.timedelta(days=4)

        Booking.objects.create(
            resource=self.car,
            user=self.user,
            created_by=self.user,
            start_at=at(self.monday, "08:00"),
            end_at=at(self.wednesday, "17:00"),
            purpose="Outstation trip",
            status=BookingStatus.APPROVED,
        )

    def count(self, start_day, start, end_day, end) -> int:
        return find_conflicts(self.car, at(start_day, start), at(end_day, end)).count()

    def test_fully_inside_is_rejected(self):
        self.assertEqual(self.count(self.tuesday, "09:00", self.tuesday, "11:00"), 1)

    def test_straddling_the_start_is_rejected(self):
        self.assertEqual(self.count(self.sunday, "20:00", self.monday, "10:00"), 1)

    def test_straddling_the_end_is_rejected(self):
        self.assertEqual(self.count(self.wednesday, "16:00", self.thursday, "09:00"), 1)

    def test_enclosing_entirely_is_rejected(self):
        self.assertEqual(self.count(self.sunday, "06:00", self.friday, "18:00"), 1)

    def test_ending_exactly_at_the_start_is_accepted(self):
        self.assertEqual(self.count(self.sunday, "20:00", self.monday, "08:00"), 0)

    def test_starting_exactly_at_the_end_is_accepted(self):
        self.assertEqual(self.count(self.wednesday, "17:00", self.thursday, "09:00"), 0)
