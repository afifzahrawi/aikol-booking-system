"""Two simultaneous submissions for the same slot must produce exactly one booking.

This is the test that proves the guarantee actually holds, rather than holding
in the absence of contention. It is also the test that shows why PostgreSQL is
required in production rather than preferred:

  - `select_for_update()` is a no-op on SQLite, which serialises writes with a
    database-wide lock instead of row locks;
  - SQLite has no exclusion constraint at all.

So on SQLite this test is skipped rather than quietly passing for the wrong
reason. A green run on the development database says nothing about concurrency;
only the PostgreSQL run does.
"""

from __future__ import annotations

import datetime as dt
import threading

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import Affiliation, User
from apps.bookings.models import Booking
from apps.bookings.services import create_booking
from apps.resources.models import Venue

from .test_conflicts import at


class ConcurrentSubmissionTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="race@demo.aikol.test",
            password="prototype-password-1",
            full_name="Race Condition",
            phone="03-6196 4000",
            affiliation=Affiliation.LECTURER,
            email_verified=True,
        )
        self.venue = Venue.objects.create(
            code="VEN-RACE",
            name="Contended Room",
            venue_type=Venue.VenueType.SEMINAR,
            location="Level 1",
            capacity=20,
        )
        self.day = timezone.localdate() + dt.timedelta(days=7)

    def test_two_simultaneous_requests_produce_exactly_one_booking(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "Row locking and the exclusion constraint need PostgreSQL. "
                "On SQLite this would pass without testing anything."
            )

        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def submit() -> None:
            try:
                barrier.wait(timeout=5)
                create_booking(
                    resource=self.venue,
                    user=self.user,
                    created_by=self.user,
                    start_at=at(self.day, "10:00"),
                    end_at=at(self.day, "12:00"),
                    purpose="Simultaneous request",
                )
            except (ValidationError, IntegrityError) as exc:
                errors.append(exc)
            finally:
                # Each thread has its own connection; leaving them open holds
                # locks that would make the assertions hang rather than fail.
                connections.close_all()

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(
            Booking.objects.filter(resource=self.venue).count(),
            1,
            "exactly one of the two simultaneous submissions may win",
        )
        self.assertEqual(len(errors), 1, "the loser must be told, not silently dropped")
