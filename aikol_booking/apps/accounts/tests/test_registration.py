"""Self-registration, verification and the role/affiliation split."""

from __future__ import annotations

import datetime as dt
import re

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.notifications.models import EmailOutbox, EmailStatus


def post_data(**overrides) -> dict:
    data = {
        "full_name": "Nurul Test",
        "email": "nurul@live.iium.edu.my",
        "identification_number": "2117001",
        "phone": "012-345 6789",
        "affiliation": Affiliation.STUDENT,
        "password1": "kulliyyah-booking-42",
        "password2": "kulliyyah-booking-42",
    }
    data.update(overrides)
    return data


class RegistrationTests(TestCase):
    url = "/register/"

    def test_an_iium_address_registers(self):
        response = self.client.post(self.url, post_data())
        self.assertRedirects(response, "/register/check-your-email/")
        user = User.objects.get(email="nurul@live.iium.edu.my")
        self.assertEqual(user.identification_number, "2117001")
        self.assertEqual(user.affiliation, Affiliation.STUDENT)
        self.assertEqual(user.role, Role.USER)

    def test_a_new_account_cannot_book_until_it_is_verified(self):
        self.client.post(self.url, post_data())
        user = User.objects.get(email="nurul@live.iium.edu.my")
        self.assertFalse(user.email_verified)
        self.assertFalse(user.can_book)

    def test_registration_queues_exactly_one_verification_email(self):
        self.client.post(self.url, post_data())
        rows = EmailOutbox.objects.filter(kind="ACCOUNT_VERIFY")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().to_address, "nurul@live.iium.edu.my")
        self.assertEqual(rows.first().status, EmailStatus.PENDING)

    def test_the_verification_email_carries_no_personal_identifiers(self):
        """Matriculation and telephone numbers are personal data. There is no
        reason for either to travel in a confirmation message."""
        self.client.post(self.url, post_data())
        body = EmailOutbox.objects.get(kind="ACCOUNT_VERIFY").body
        self.assertNotIn("2117001", body)
        self.assertNotIn("012-345 6789", body)

    def test_a_non_iium_address_is_refused_unless_the_box_is_ticked(self):
        response = self.client.post(self.url, post_data(email="someone@gmail.com"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use your IIUM address")
        self.assertFalse(User.objects.filter(email="someone@gmail.com").exists())

    def test_a_member_of_the_public_registers_by_ticking_the_box(self):
        response = self.client.post(
            self.url,
            post_data(email="someone@gmail.com", identification_number="", not_iium="on"),
        )
        self.assertRedirects(response, "/register/check-your-email/")
        user = User.objects.get(email="someone@gmail.com")
        self.assertEqual(user.affiliation, Affiliation.PUBLIC)
        # NULL, not an empty string: the column is unique and a second empty
        # string would collide.
        self.assertIsNone(user.identification_number)

    def test_two_members_of_the_public_can_both_register(self):
        self.client.post(self.url, post_data(email="a@gmail.com", identification_number="", not_iium="on"))
        self.client.post(self.url, post_data(email="b@gmail.com", identification_number="", not_iium="on"))
        self.assertEqual(User.objects.filter(affiliation=Affiliation.PUBLIC).count(), 2)

    def test_ticking_the_box_with_an_iium_address_is_refused(self):
        response = self.client.post(self.url, post_data(identification_number="", not_iium="on"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That is an IIUM address")

    def test_an_iium_address_without_a_number_is_refused(self):
        response = self.client.post(self.url, post_data(identification_number=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "matriculation or staff number")
        self.assertFalse(User.objects.filter(email="nurul@live.iium.edu.my").exists())

    def test_a_duplicate_address_creates_no_second_account_and_says_nothing(self):
        """This test used to assert the message "An account already exists".

        That message was an address oracle — anybody could submit a list and
        learn which colleagues had registered — and the security review removed
        it. The registration now looks identical either way and the existing
        account is emailed instead. The behaviour under test is unchanged where
        it matters: still exactly one account.

        See test_security.EnumerationTests for the full set.
        """
        self.client.post(self.url, post_data())
        response = self.client.post(self.url, post_data(identification_number="2117002"))
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(response, "already exists", status_code=302)
        self.assertEqual(User.objects.count(), 1)

    def test_a_duplicate_identification_number_is_refused(self):
        self.client.post(self.url, post_data())
        response = self.client.post(self.url, post_data(email="other@iium.edu.my"))
        self.assertContains(response, "already registered")
        self.assertEqual(User.objects.count(), 1)


class VerificationTests(TestCase):
    def setUp(self) -> None:
        self.client.post("/register/", post_data())
        self.user = User.objects.get(email="nurul@live.iium.edu.my")
        body = EmailOutbox.objects.get(kind="ACCOUNT_VERIFY").body
        self.link = re.search(r"(/verify/\S+)", body).group(1)

    def test_following_the_link_verifies_the_address(self):
        response = self.client.get(self.link)
        self.assertRedirects(response, reverse("accounts:login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertTrue(self.user.can_book)

    def test_the_link_stops_working_once_it_is_used(self):
        """The token is derived from `email_verified`, so using it invalidates
        it with nothing to store or clean up."""
        self.client.get(self.link)
        response = self.client.get(self.link)
        self.assertEqual(response.status_code, 400)

    def test_a_tampered_token_is_refused(self):
        # Change the token, keeping the trailing slash — without it Django's
        # APPEND_SLASH redirects and the view is never reached, so the test
        # would pass for the wrong reason.
        uidb64, _token = self.link.strip("/").split("/")[1:3]
        bad = f"/verify/{uidb64}/aaaaaa-0000000000000000000000000000000000000000/"
        self.assertEqual(self.client.get(bad).status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)


class AuthorityTests(TestCase):
    """Role is what you may do; affiliation is what you are. They vary
    independently, which is why they are separate fields."""

    def make(self, **extra) -> User:
        return User.objects.create_user(
            email=extra.pop("email", "person@demo.aikol.test"),
            password="prototype-password-1",
            full_name="Person",
            phone="03-6196 4000",
            **extra,
        )

    def test_an_administrator_is_also_an_approver(self):
        user = self.make(role=Role.ADMINISTRATOR)
        self.assertTrue(user.is_administrator)
        self.assertTrue(user.is_approver)

    def test_an_approver_is_not_an_administrator(self):
        user = self.make(role=Role.APPROVER)
        self.assertTrue(user.is_approver)
        self.assertFalse(user.is_administrator)

    def test_a_lecturer_may_drive_and_a_student_may_not(self):
        self.assertTrue(self.make(email="l@demo.aikol.test", affiliation=Affiliation.LECTURER).may_drive)
        self.assertFalse(self.make(email="s@demo.aikol.test", affiliation=Affiliation.STUDENT).may_drive)

    def test_a_lecturer_can_still_be_an_ordinary_user(self):
        user = self.make(affiliation=Affiliation.LECTURER, role=Role.USER)
        self.assertTrue(user.may_drive)
        self.assertFalse(user.is_approver)

    def test_a_deactivated_account_cannot_book(self):
        user = self.make(email="off@demo.aikol.test", email_verified=True, is_active=False)
        self.assertFalse(user.can_book)


class LoginTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="signin@demo.aikol.test",
            password="prototype-password-1",
            full_name="Sign In",
            phone="03-6196 4000",
            email_verified=True,
        )

    def test_sign_in_with_an_email_address(self):
        ok = self.client.login(username="signin@demo.aikol.test", password="prototype-password-1")
        self.assertTrue(ok)

    def test_the_address_is_not_case_sensitive_at_the_form(self):
        response = self.client.post(
            "/sign-in/",
            {"username": "SignIn@Demo.Aikol.Test", "password": "prototype-password-1"},
        )
        self.assertRedirects(response, "/")

    def test_the_dashboard_needs_a_signed_in_user(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sign-in/", response["Location"])


class SettingsSeedTests(TestCase):
    def test_seeding_is_idempotent_and_carries_the_confirmed_values(self):
        from apps.administration.models import SystemSetting

        first = SystemSetting.seed()
        second = SystemSetting.seed()
        self.assertGreater(first, 0)
        self.assertEqual(second, 0, "a second run creates nothing")
        self.assertEqual(SystemSetting.get_int("advance_booking_limit_days"), 90)
        self.assertEqual(SystemSetting.get_int("maximum_booking_minutes"), 540)
        self.assertEqual(SystemSetting.get("bookable_window_start"), "08:00")
        self.assertEqual(SystemSetting.get("bookable_window_end"), "22:00")
        self.assertEqual(SystemSetting.get_int("cancellation_cutoff_hours"), 72)
        self.assertEqual(SystemSetting.get_int("booking_retention_years"), 7)
        self.assertEqual(SystemSetting.get("retention_disposal_action"), "EXPORT")


class CancellationCutoffTests(TestCase):
    """Decision 12: a user cancels their own booking freely, up to three days
    before. Approvers are not bound by the cutoff — they handle the exceptions."""

    def setUp(self) -> None:
        from apps.administration.models import SystemSetting
        from apps.bookings.models import Booking
        from apps.resources.models import Venue

        SystemSetting.seed()
        self.owner = User.objects.create_user(
            email="owner@demo.aikol.test", password="prototype-password-1",
            full_name="Owner", phone="03-6196 4000", email_verified=True,
        )
        self.other = User.objects.create_user(
            email="other@demo.aikol.test", password="prototype-password-1",
            full_name="Other", phone="03-6196 4000", email_verified=True,
        )
        self.approver = User.objects.create_user(
            email="approver@demo.aikol.test", password="prototype-password-1",
            full_name="Approver", phone="03-6196 4000", email_verified=True,
            role=Role.APPROVER,
        )
        venue = Venue.objects.create(
            code="VEN-C", name="Discussion Room", venue_type=Venue.VenueType.DISCUSSION,
            location="Level 1", capacity=10,
        )
        self.far = Booking.objects.create(
            resource=venue, user=self.owner, created_by=self.owner,
            start_at=timezone.now() + dt.timedelta(days=10),
            end_at=timezone.now() + dt.timedelta(days=10, hours=2),
            purpose="Far off",
        )
        self.soon = Booking.objects.create(
            resource=venue, user=self.owner, created_by=self.owner,
            start_at=timezone.now() + dt.timedelta(hours=24),
            end_at=timezone.now() + dt.timedelta(hours=26),
            purpose="Tomorrow",
        )

    def test_the_owner_may_cancel_well_in_advance(self):
        self.assertTrue(self.far.can_be_cancelled_by(self.owner))

    def test_the_owner_may_not_cancel_inside_the_three_day_cutoff(self):
        self.assertFalse(self.soon.can_be_cancelled_by(self.owner))

    def test_an_approver_is_not_bound_by_the_cutoff(self):
        self.assertTrue(self.soon.can_be_cancelled_by(self.approver))

    def test_somebody_else_may_not_cancel_your_booking(self):
        self.assertFalse(self.far.can_be_cancelled_by(self.other))
