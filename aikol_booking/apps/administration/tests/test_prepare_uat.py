from __future__ import annotations

import datetime as dt
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.administration.models import SystemSetting
from apps.administration.tests.test_deletion import make_user
from apps.audit.models import AuditLog
from apps.bookings.models import Booking, BookingStatus
from apps.resources.models import Venue


def run(*args):
    out = StringIO()
    call_command("prepare_uat", *args, stdout=out)
    return out.getvalue()


class PrepareUatTests(TestCase):
    def setUp(self):
        self.person = make_user("someone@demo.aikol.test")
        self.admin = make_user("office@demo.aikol.test", Role.ADMINISTRATOR)
        self.test_room = Venue.objects.create(
            code="TEST-01", name="Test Venue", venue_type=Venue.VenueType.MEETING,
            location="L1", capacity=5,
        )
        self.real_room = Venue.objects.create(
            code="AIKOL-MR-01", name="Meeting Room A", venue_type=Venue.VenueType.MEETING,
            location="L3", capacity=16,
        )
        start = timezone.now() + dt.timedelta(days=3)
        for room in (self.test_room, self.real_room):
            Booking.objects.create(
                resource=room, user=self.person, created_by=self.person, start_at=start,
                end_at=start + dt.timedelta(hours=1), purpose="x", status=BookingStatus.PENDING,
            )
        AuditLog.objects.create(action="booking.submitted", actor=self.person)
        self.settings_before = SystemSetting.objects.count()

    def test_without_confirm_nothing_changes(self):
        output = run()
        self.assertIn("Test venue to delete: TEST-01", output)
        self.assertEqual(Booking.objects.count(), 2)
        self.assertTrue(Venue.objects.filter(code="TEST-01").exists())

    def test_confirm_clears_history_and_swaps_venues(self):
        run("--confirm")
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(AuditLog.objects.exists())
        self.assertFalse(Venue.objects.filter(code="TEST-01").exists())
        self.assertTrue(Venue.objects.filter(code="AIKOL-MR-01").exists())
        uat = Venue.objects.filter(code__startswith="UAT-VEN-").order_by("code")
        self.assertEqual(
            [v.image_slug for v in uat], ["moot-court", "seminar-a", "meeting-a"]
        )
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(SystemSetting.objects.count(), self.settings_before)

    def test_refuses_once_uat_bookings_exist(self):
        run("--confirm")
        room = Venue.objects.get(code="UAT-VEN-01")
        start = timezone.now() + dt.timedelta(days=5)
        Booking.objects.create(
            resource=room, user=self.person, created_by=self.person, start_at=start,
            end_at=start + dt.timedelta(hours=1), purpose="x", status=BookingStatus.PENDING,
        )
        with self.assertRaises(CommandError):
            run("--confirm")
        self.assertEqual(Booking.objects.count(), 1)
