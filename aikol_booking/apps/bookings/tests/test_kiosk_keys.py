"""The office kiosk, Admin confirmation of key records, and vehicle mileage."""

from __future__ import annotations

import datetime as dt
import io
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.bookings.keys import (
    awaiting_confirmation,
    confirm_key_entry,
    issue_key,
    reject_key_entry,
    return_key,
)
from apps.bookings.models import Booking, BookingStatus, KeyHandover, ManagementDecision, Via
from apps.resources.models import Vehicle

from .test_conflicts import at
from .test_keys import KeyFixtures

MEDIA = tempfile.mkdtemp()


def png_upload(name="receipt.png"):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class VehicleFixtures(KeyFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1111",
            make="Perodua", model="Bezza", year=2023, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=200),
        )
        later = self.day + dt.timedelta(days=1)
        self.trip = Booking.objects.create(
            resource=self.car, user=self.owner, created_by=self.owner,
            start_at=at(later, "08:00"), end_at=at(later, "17:00"),
            purpose="Court visit", status=BookingStatus.APPROVED,
            management_status=ManagementDecision.APPROVED,
        )


class ConfirmationTests(VehicleFixtures):
    def test_an_office_entry_is_confirmed_as_it_is_made(self):
        handover = issue_key(self.booking, issued_by=self.clerk)
        self.assertFalse(handover.issue_pending)
        self.assertEqual(handover.issue_confirmed_by, self.clerk)
        self.assertFalse(awaiting_confirmation().exists())

    def test_a_kiosk_entry_waits_for_the_admin(self):
        handover = issue_key(self.booking, issued_by=self.admin, via=Via.KIOSK)
        self.assertTrue(handover.issue_pending)
        self.assertEqual(handover.state, "Collection awaiting confirmation")
        self.assertIn(handover, awaiting_confirmation())

        handover = confirm_key_entry(handover, "issue", confirmed_by=self.clerk)
        self.assertFalse(handover.issue_pending)
        self.assertEqual(handover.issued_by, self.clerk)
        self.assertFalse(awaiting_confirmation().exists())

    def test_rejecting_a_kiosk_collection_clears_it_and_keeps_the_row(self):
        handover = issue_key(
            self.booking, issued_by=self.admin, collected_by_name="Aiman", via=Via.KIOSK
        )
        handover = reject_key_entry(handover, "issue")
        self.assertIsNone(handover.issued_at)
        self.assertEqual(handover.collected_by_name, "")
        self.assertTrue(KeyHandover.objects.filter(pk=handover.pk).exists())
        # The booking is back in the queue awaiting collection.
        issue_key(self.booking, issued_by=self.clerk)

    def test_a_kiosk_return_waits_and_can_be_rejected(self):
        issue_key(self.booking, issued_by=self.clerk)
        handover = return_key(
            self.booking, returned_to=self.admin, returned_by_name="Siti", via=Via.KIOSK
        )
        self.assertTrue(handover.return_pending)
        handover = reject_key_entry(handover, "return")
        self.assertIsNone(handover.returned_at)
        self.assertEqual(handover.state, "Issued")

    def test_nothing_pending_cannot_be_confirmed(self):
        handover = issue_key(self.booking, issued_by=self.clerk)
        with self.assertRaises(ValidationError):
            confirm_key_entry(handover, "issue", confirmed_by=self.clerk)


@override_settings(MEDIA_ROOT=MEDIA)
class MileageTests(VehicleFixtures):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_mileage_is_optional(self):
        handover = issue_key(self.trip, issued_by=self.clerk)
        handover = return_key(self.trip, returned_to=self.clerk, returned_by_name="Driver")
        self.assertIsNone(handover.mileage_out)
        self.assertIsNone(handover.mileage_in)

    def test_mileage_and_receipt_are_kept_for_a_vehicle(self):
        issue_key(self.trip, issued_by=self.clerk, mileage_out=40100)
        handover = return_key(
            self.trip, returned_to=self.clerk, returned_by_name="Driver",
            mileage_in=40250, fuel_receipt=png_upload(),
        )
        self.assertEqual((handover.mileage_out, handover.mileage_in), (40100, 40250))
        self.assertTrue(handover.fuel_receipt.name.startswith("fuel-receipts/"))

    def test_mileage_cannot_go_backwards(self):
        issue_key(self.trip, issued_by=self.clerk, mileage_out=40100)
        with self.assertRaises(ValidationError):
            return_key(
                self.trip, returned_to=self.clerk, returned_by_name="Driver", mileage_in=39000
            )

    def test_a_venue_key_never_records_mileage(self):
        handover = issue_key(self.booking, issued_by=self.clerk, mileage_out=100)
        self.assertIsNone(handover.mileage_out)

    def test_the_return_screen_asks_for_mileage_only_on_a_vehicle(self):
        self.client.force_login(self.admin)
        issue_key(self.trip, issued_by=self.clerk)
        issue_key(self.booking, issued_by=self.clerk)
        car = self.client.get(reverse("bookings:key_return", args=[self.trip.pk]))
        room = self.client.get(reverse("bookings:key_return", args=[self.booking.pk]))
        self.assertContains(car, "Petrol receipt")
        self.assertContains(car, "Mileage when returned")
        self.assertNotContains(room, "Petrol receipt")

    def test_the_receipt_is_uploaded_through_the_return_screen(self):
        self.client.force_login(self.admin)
        issue_key(self.trip, issued_by=self.clerk, mileage_out=10)
        response = self.client.post(
            reverse("bookings:key_return", args=[self.trip.pk]),
            {"returned_by_name": "Driver", "mileage_in": "120", "fuel_receipt": png_upload()},
        )
        self.assertEqual(response.status_code, 302)
        handover = KeyHandover.objects.get(booking=self.trip)
        self.assertEqual(handover.mileage_in, 120)
        self.assertTrue(handover.fuel_receipt)
        log = AuditLog.objects.filter(action="KEY_RETURNED").latest("pk")
        self.assertIn("Mileage in 120 km", log.description)


class RegisterTests(VehicleFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.admin)

    def test_venue_and_vehicle_keys_are_listed_apart(self):
        url = reverse("bookings:keys")
        rooms = self.client.get(url, {"kind": "venue"})
        cars = self.client.get(url, {"kind": "vehicle"})
        self.assertContains(rooms, self.booking.booking_reference)
        self.assertNotContains(rooms, self.trip.booking_reference)
        self.assertContains(cars, self.trip.booking_reference)
        self.assertNotContains(cars, self.booking.booking_reference)

    def test_search_by_booking_number(self):
        other = Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=at(self.day, "14:00"), end_at=at(self.day, "15:00"),
            purpose="Other", status=BookingStatus.APPROVED,
        )
        response = self.client.get(
            reverse("bookings:keys"), {"q": other.booking_reference[-4:].lower()}
        )
        self.assertContains(response, other.booking_reference)
        response = self.client.get(reverse("bookings:keys"), {"q": other.booking_reference})
        self.assertNotContains(response, self.booking.booking_reference)

    def test_confirm_and_reject_buttons(self):
        handover = issue_key(self.booking, issued_by=self.admin, via=Via.KIOSK)
        page = self.client.get(reverse("bookings:keys"), {"tab": "confirm"})
        self.assertContains(page, self.booking.booking_reference)
        self.client.post(
            reverse("bookings:key_confirm", args=[handover.pk, "issue"]), {"decision": "confirm"}
        )
        handover.refresh_from_db()
        self.assertFalse(handover.issue_pending)
        self.assertTrue(AuditLog.objects.filter(action="KEY_ISSUE_CONFIRMED").exists())

    def test_a_requester_cannot_confirm(self):
        handover = issue_key(self.booking, issued_by=self.admin, via=Via.KIOSK)
        self.client.force_login(self.plain)
        response = self.client.post(
            reverse("bookings:key_confirm", args=[handover.pk, "issue"]), {"decision": "confirm"}
        )
        self.assertEqual(response.status_code, 403)


class KioskTests(VehicleFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.admin)
        self.client.get(reverse("bookings:kiosk"))

    def test_the_kiosk_session_reaches_nothing_else(self):
        for name in ("bookings:keys", "bookings:manage", "administration:users"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse("bookings:kiosk"))

    def test_the_kiosk_hides_the_navigation(self):
        response = self.client.get(reverse("bookings:kiosk"))
        self.assertNotContains(response, 'class="app-nav"')

    def test_collecting_at_the_kiosk_waits_for_confirmation(self):
        response = self.client.post(
            reverse("bookings:kiosk"), {"reference": self.booking.booking_reference.lower()}
        )
        self.assertRedirects(
            response, reverse("bookings:kiosk_booking", args=[self.booking.booking_reference])
        )
        response = self.client.post(
            reverse("bookings:kiosk_booking", args=[self.booking.booking_reference]),
            {"collected_by_name": "", "collected_by_contact": ""},
        )
        self.assertRedirects(response, reverse("bookings:kiosk"))
        handover = KeyHandover.objects.get(booking=self.booking)
        self.assertTrue(handover.issue_pending)
        self.assertEqual(handover.issue_via, Via.KIOSK)
        self.assertTrue(AuditLog.objects.filter(action="KEY_ISSUED_KIOSK").exists())

    def test_returning_a_car_at_the_kiosk(self):
        issue_key(self.trip, issued_by=self.clerk, mileage_out=500)
        page = self.client.get(
            reverse("bookings:kiosk_booking", args=[self.trip.booking_reference])
        )
        self.assertContains(page, "I am returning the key")
        self.client.post(
            reverse("bookings:kiosk_booking", args=[self.trip.booking_reference]),
            {"returned_by_name": "Driver", "mileage_in": "650"},
        )
        handover = KeyHandover.objects.get(booking=self.trip)
        self.assertTrue(handover.return_pending)
        self.assertEqual(handover.mileage_in, 650)

    def test_an_unknown_number_says_so(self):
        response = self.client.post(reverse("bookings:kiosk"), {"reference": "BK-NOPE"})
        self.assertContains(response, "No booking has that number")

    def test_leaving_needs_the_admin_password(self):
        exit_url = reverse("bookings:kiosk_exit")
        response = self.client.post(exit_url, {"password": "wrong"})
        self.assertContains(response, "not right")
        self.assertRedirects(self.client.get(reverse("bookings:keys")), reverse("bookings:kiosk"))
        response = self.client.post(exit_url, {"password": "prototype-password-1"})
        self.assertRedirects(response, reverse("bookings:keys"))
        self.assertEqual(self.client.get(reverse("bookings:keys")).status_code, 200)

    def test_a_requester_cannot_open_the_kiosk(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(reverse("bookings:kiosk")).status_code, 403)
