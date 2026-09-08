"""Key custody, booking on behalf, and the administration screens."""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.administration.models import SystemSetting
from apps.audit.models import AuditLog
from apps.bookings.keys import (
    issue_key,
    keys_awaiting_collection,
    outstanding_keys,
    return_key,
)
from apps.bookings.models import Booking, BookingStatus, KeyHandover
from apps.resources.models import Vehicle, Venue

from .test_conflicts import at


def make_user(email: str, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name=extra.pop("full_name", email.split("@")[0].title()),
        phone="012-345 6789",
        email_verified=True,
        **extra,
    )


class KeyFixtures(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        self.admin = make_user("admin@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.clerk = make_user("clerk@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.owner = make_user("owner@demo.aikol.test", affiliation=Affiliation.LECTURER)
        self.plain = make_user("plain@demo.aikol.test")
        self.room = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        self.day = timezone.localdate() + dt.timedelta(days=7)
        self.booking = Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"),
            purpose="Tutorial", status=BookingStatus.APPROVED,
        )


class KeyCustodyTests(KeyFixtures):
    def test_issuing_records_four_separate_people(self):
        """Who booked, who collected, who issued, and later who received it
        back. Assuming any two are the same person is what makes a custody
        record worthless."""
        handover = issue_key(
            self.booking,
            issued_by=self.clerk,
            collected_by_name="Aiman bin Hassan",
            collected_by_contact="019-222 3344",
        )
        self.assertEqual(self.booking.user, self.owner)
        self.assertEqual(handover.issued_by, self.clerk)
        self.assertEqual(handover.collected_by_name, "Aiman bin Hassan")
        self.assertIsNotNone(handover.issued_at)
        self.assertIsNone(handover.returned_at)

        handover = return_key(
            self.booking, returned_to=self.admin, returned_by_name="Siti binti Omar"
        )
        self.assertEqual(handover.returned_to, self.admin)
        self.assertEqual(handover.returned_by_name, "Siti binti Omar")
        self.assertNotEqual(handover.issued_by, handover.returned_to)

    def test_a_key_cannot_be_issued_for_a_pending_booking(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=["status"])
        with self.assertRaises(ValidationError) as ctx:
            issue_key(self.booking, issued_by=self.clerk, collected_by_name="Somebody")
        self.assertIn("only for an approved booking", str(ctx.exception))
        self.assertEqual(KeyHandover.objects.count(), 0)

    def test_the_collector_must_be_named(self):
        with self.assertRaises(ValidationError) as ctx:
            issue_key(self.booking, issued_by=self.clerk, collected_by_name="   ")
        self.assertIn("often not the person who booked", str(ctx.exception))

    def test_a_key_cannot_be_issued_twice(self):
        issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        with self.assertRaises(ValidationError) as ctx:
            issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        self.assertIn("was issued on", str(ctx.exception))

    def test_a_key_that_was_never_issued_cannot_be_returned(self):
        with self.assertRaises(ValidationError) as ctx:
            return_key(self.booking, returned_to=self.admin, returned_by_name="Aiman")
        self.assertIn("No key was issued", str(ctx.exception))

    def test_a_key_cannot_be_returned_twice(self):
        issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        return_key(self.booking, returned_to=self.admin, returned_by_name="Aiman")
        with self.assertRaises(ValidationError):
            return_key(self.booking, returned_to=self.admin, returned_by_name="Aiman")

    def test_an_outstanding_key_survives_the_booking_being_completed(self):
        """The two are tracked separately on purpose. A booking whose period has
        ended is exactly the case worth chasing, not one to file away."""
        issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        self.booking.status = BookingStatus.COMPLETED
        self.booking.save(update_fields=["status"])
        self.assertEqual(outstanding_keys().count(), 1)

    def test_a_returned_key_leaves_the_outstanding_list(self):
        issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        return_key(self.booking, returned_to=self.admin, returned_by_name="Aiman")
        self.assertEqual(outstanding_keys().count(), 0)

    def test_awaiting_collection_lists_approved_bookings_with_no_key_out(self):
        self.assertIn(self.booking, keys_awaiting_collection())
        issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        self.assertNotIn(self.booking, keys_awaiting_collection())

    def test_a_pending_booking_is_not_awaiting_collection(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=["status"])
        self.assertNotIn(self.booking, keys_awaiting_collection())


class KeyViewTests(KeyFixtures):
    def test_only_an_administrator_reaches_the_key_register(self):
        """Keys are held by the office personally (decision 16)."""
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(reverse("bookings:keys")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("bookings:keys")).status_code, 200)

    def test_issuing_through_the_screen_writes_to_the_audit_log(self):
        self.client.force_login(self.clerk)
        response = self.client.post(
            reverse("bookings:key_issue", args=[self.booking.pk]),
            {"collected_by_name": "Aiman bin Hassan", "collected_by_contact": "019-222 3344"},
        )
        self.assertEqual(response.status_code, 302)
        entry = AuditLog.objects.get(action="KEY_ISSUED")
        self.assertIn("Aiman bin Hassan", entry.description)
        # The collector's telephone number is personal data and has no business
        # in the log's free text.
        self.assertNotIn("019-222 3344", entry.description)

    def test_returning_through_the_screen_is_logged(self):
        issue_key(self.booking, issued_by=self.clerk, collected_by_name="Aiman")
        self.client.force_login(self.admin)
        self.client.post(
            reverse("bookings:key_return", args=[self.booking.pk]),
            {"returned_by_name": "Siti binti Omar", "condition_notes": "All in order"},
        )
        self.assertTrue(AuditLog.objects.filter(action="KEY_RETURNED").exists())
        handover = KeyHandover.objects.get()
        self.assertEqual(handover.condition_notes, "All in order")

    def test_an_overdue_key_is_flagged_on_the_register(self):
        past = Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=timezone.now() - dt.timedelta(days=2),
            end_at=timezone.now() - dt.timedelta(days=2) + dt.timedelta(hours=2),
            purpose="Last week", status=BookingStatus.COMPLETED,
        )
        KeyHandover.objects.create(
            booking=past, issued_at=timezone.now() - dt.timedelta(days=2), issued_by=self.clerk,
            collected_by_name="Aiman",
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("bookings:keys"))
        self.assertContains(response, "Overdue")


class OnBehalfTests(KeyFixtures):
    """Decision 14. The booking is attributed to both people, honestly."""

    def post(self, actor, **overrides):
        self.client.force_login(actor)
        data = {
            "start_date": (self.day + dt.timedelta(days=3)).isoformat(),
            "start_time": "14:00",
            "end_time": "16:00",
            "purpose": "Departmental meeting",
            "attendees": "8",
        }
        data.update(overrides)
        return self.client.post(reverse("bookings:create", args=[self.room.pk]), data)

    def test_an_administrator_books_for_somebody_else(self):
        response = self.post(self.admin, on_behalf_of=str(self.owner.pk))
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.exclude(pk=self.booking.pk).get()
        self.assertEqual(booking.user, self.owner, "the booking is FOR the lecturer")
        self.assertEqual(booking.created_by, self.admin, "and BY the administrator")

    def test_it_is_written_to_the_audit_log(self):
        self.post(self.admin, on_behalf_of=str(self.owner.pk))
        entry = AuditLog.objects.get(action="BOOKING_ON_BEHALF")
        self.assertEqual(entry.actor, self.admin)
        self.assertIn(self.owner.full_name, entry.description)

    def test_the_confirmation_goes_to_the_person_it_is_for(self):
        from apps.notifications.models import EmailOutbox

        self.post(self.admin, on_behalf_of=str(self.owner.pk))
        row = EmailOutbox.objects.filter(kind="BOOKING_SUBMITTED").latest("id")
        self.assertEqual(row.to_address, self.owner.email)
        self.assertNotEqual(row.to_address, self.admin.email)

    def test_an_ordinary_user_has_no_such_field(self):
        """And so cannot book for anyone else by posting the parameter."""
        self.post(self.plain, on_behalf_of=str(self.owner.pk))
        booking = Booking.objects.exclude(pk=self.booking.pk).get()
        self.assertEqual(booking.user, self.plain)
        self.assertEqual(booking.created_by, self.plain)

    def test_eligibility_to_drive_belongs_to_the_person_it_is_for(self):
        """An administrator who may drive must not confer that on a student by
        typing the form on their behalf."""
        car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1111",
            make="Perodua", model="Bezza", year=2023, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=200),
        )
        student = make_user("student@demo.aikol.test", affiliation=Affiliation.STUDENT)
        self.admin.affiliation = Affiliation.STAFF
        self.admin.licence_number = "D1234567"
        self.admin.licence_expiry = timezone.localdate() + dt.timedelta(days=400)
        self.admin.save()

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("bookings:create", args=[car.pk]),
            {
                "start_date": (self.day + dt.timedelta(days=3)).isoformat(),
                "start_time": "08:00", "end_time": "17:00",
                "purpose": "Fieldwork", "driver_arrangement": "SELF",
                "location_from": "AIKOL", "location_to": "Putrajaya", "passengers": "3",
                "on_behalf_of": str(student.pk),
            },
        )
        self.assertContains(response, "Only lecturers and staff may drive")
        self.assertFalse(Booking.objects.filter(resource=car).exists())


class AdministrationScreenTests(KeyFixtures):
    SCREENS = ("dashboard", "users", "settings", "site_content", "audit")

    def test_an_ordinary_user_is_refused_every_administration_screen(self):
        self.client.force_login(self.plain)
        for name in self.SCREENS:
            with self.subTest(screen=name):
                self.assertEqual(
                    self.client.get(reverse(f"administration:{name}")).status_code, 403
                )

    def test_an_approver_is_refused_them_too(self):
        approver = make_user("approver@demo.aikol.test", role=Role.APPROVER)
        self.client.force_login(approver)
        for name in self.SCREENS:
            with self.subTest(screen=name):
                self.assertEqual(
                    self.client.get(reverse(f"administration:{name}")).status_code, 403
                )

    def test_an_administrator_reaches_them_all(self):
        self.client.force_login(self.admin)
        for name in self.SCREENS:
            with self.subTest(screen=name):
                self.assertEqual(
                    self.client.get(reverse(f"administration:{name}")).status_code, 200
                )

    def test_deactivating_a_user_is_logged_and_never_deletes(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("administration:user_edit", args=[self.owner.pk]),
            {
                "full_name": self.owner.full_name, "email": self.owner.email,
                "identification_number": "", "phone": self.owner.phone,
                "affiliation": self.owner.affiliation, "role": self.owner.role,
                "email_verified": "on",
            },
        )
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="USER_DEACTIVATED").exists())

    def test_the_user_form_offers_no_password_field(self):
        """An administrator who can set someone else's password is a liability,
        and the reset flow already exists."""
        from apps.administration.forms import UserAdminForm

        self.assertNotIn("password", UserAdminForm().fields)

    def test_changing_a_setting_records_the_old_and_new_value(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("administration:settings"),
            {"key": "maximum_vehicle_trip_days", "value": "10"},
        )
        self.assertEqual(SystemSetting.get_int("maximum_vehicle_trip_days"), 10)
        entry = AuditLog.objects.get(action="SETTING_CHANGED")
        self.assertIn("7 to 10", entry.description)

    def test_the_audit_screen_offers_nothing_that_writes(self):
        """Scoped to the page's own content: the sign-out control in the shared
        chrome is a POST form on every page and is not what this is about."""
        self.client.force_login(self.admin)
        html = self.client.get(reverse("administration:audit")).content.decode()
        body = html[html.index("<main") : html.index("</main>")]
        self.assertNotIn('method="post"', body)
        # For contrast: the settings screen is a write screen and does have one.
        settings_html = self.client.get(reverse("administration:settings")).content.decode()
        settings_body = settings_html[
            settings_html.index("<main") : settings_html.index("</main>")
        ]
        self.assertIn('method="post"', settings_body)
