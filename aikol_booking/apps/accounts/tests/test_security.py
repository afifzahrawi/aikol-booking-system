"""Phase 8: the security review, as tests rather than a checklist.

Everything here corresponds to a row in docs/technical/security.md. A checklist
that nobody re-reads decays; a test fails.
"""

from __future__ import annotations

import datetime as dt

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.accounts.throttle import LIMITS
from apps.administration.models import SystemSetting
from apps.audit.models import AuditLog
from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import EmailOutbox
from apps.resources.models import Venue


def make_user(email: str, **extra) -> User:
    return User.objects.create_user(
        email=email, password="prototype-password-1",
        full_name=extra.pop("full_name", "Person"), phone="012-345 6789",
        email_verified=True, **extra,
    )


REGISTRATION = {
    "full_name": "Nurul Test", "email": "nurul@live.iium.edu.my",
    "identification_number": "2117001", "phone": "012-345 6789",
    "affiliation": Affiliation.STUDENT,
    "password1": "kulliyyah-booking-42", "password2": "kulliyyah-booking-42",
}


class EnumerationTests(TestCase):
    """A form that says "an account already exists" is an address oracle:
    submit a list, read the errors, learn who has an account here."""

    def setUp(self) -> None:
        cache.clear()
        self.existing = make_user("nurul@live.iium.edu.my", full_name="Nurul Existing")

    def test_registering_a_known_address_looks_exactly_like_a_new_one(self):
        fresh = self.client.post("/register/", dict(REGISTRATION, email="new@iium.edu.my",
                                                    identification_number="2117999"))
        cache.clear()
        known = self.client.post("/register/", REGISTRATION)
        self.assertEqual(fresh.status_code, known.status_code)
        self.assertEqual(fresh["Location"], known["Location"])

    def test_no_second_account_is_created(self):
        self.client.post("/register/", REGISTRATION)
        self.assertEqual(User.objects.filter(email="nurul@live.iium.edu.my").count(), 1)

    def test_the_existing_account_is_told_instead(self):
        self.client.post("/register/", REGISTRATION)
        row = EmailOutbox.objects.get(kind="ACCOUNT_DUPLICATE_ATTEMPT")
        self.assertEqual(row.to_address, self.existing.email)
        self.assertIn("already have an account", row.body)

    def test_the_attempt_is_logged(self):
        self.client.post("/register/", REGISTRATION)
        self.assertTrue(AuditLog.objects.filter(action="ACCOUNT_REGISTER_DUPLICATE").exists())

    def test_a_duplicate_matriculation_number_IS_reported(self):
        """Not an oracle — a matriculation number cannot be probed for a list of
        people the way an address can, and a silent merge of two people onto one
        number would corrupt the booking record."""
        self.existing.identification_number = "2117001"
        self.existing.save(update_fields=["identification_number"])
        response = self.client.post(
            "/register/", dict(REGISTRATION, email="someone@iium.edu.my")
        )
        self.assertContains(response, "already registered")

    def test_password_reset_says_the_same_thing_either_way(self):
        known = self.client.post("/password-reset/", {"email": self.existing.email})
        unknown = self.client.post("/password-reset/", {"email": "nobody@iium.edu.my"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known["Location"], unknown["Location"])


class ThrottleTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = make_user("person@demo.aikol.test")

    def tearDown(self) -> None:
        cache.clear()

    def test_sign_in_is_rate_limited(self):
        limit = LIMITS["login"].attempts
        for _ in range(limit):
            self.client.post("/sign-in/", {"username": self.user.email, "password": "wrong"})
        response = self.client.post(
            "/sign-in/", {"username": self.user.email, "password": "wrong"}
        )
        self.assertEqual(response.status_code, 429)

    def test_the_refusal_does_not_say_whether_the_account_exists(self):
        for _ in range(LIMITS["login"].attempts + 1):
            self.client.post("/sign-in/", {"username": "ghost@iium.edu.my", "password": "x"})
        response = self.client.post(
            "/sign-in/", {"username": "ghost@iium.edu.my", "password": "x"}
        )
        self.assertEqual(response.status_code, 429)
        body = response.content.decode().lower()
        self.assertNotIn("no account", body)
        self.assertNotIn("does not exist", body)

    def test_a_successful_sign_in_clears_the_identifier_bucket(self):
        """Somebody who finally remembers their password must not stay locked
        out by their own typos.

        The final request comes from a different address so the test measures
        the identifier bucket and not the IP one — they are separate on purpose,
        and the next test pins down that the IP bucket is NOT cleared.
        """
        for _ in range(LIMITS["login"].attempts - 1):
            self.client.post("/sign-in/", {"username": self.user.email, "password": "wrong"},
                             REMOTE_ADDR="10.0.0.1")
        self.client.post(
            "/sign-in/", {"username": self.user.email, "password": "prototype-password-1"},
            REMOTE_ADDR="10.0.0.1",
        )
        self.client.logout()
        response = self.client.post(
            "/sign-in/", {"username": self.user.email, "password": "wrong"},
            REMOTE_ADDR="10.0.0.2",
        )
        self.assertNotEqual(response.status_code, 429)

    def test_a_successful_sign_in_does_NOT_clear_the_ip_bucket(self):
        """Otherwise one valid account is a key to unlimited attempts on every
        other account from the same machine."""
        for i in range(LIMITS["login"].attempts):
            self.client.post("/sign-in/", {"username": f"v{i}@iium.edu.my", "password": "x"},
                             REMOTE_ADDR="10.0.0.9")
        self.client.post(
            "/sign-in/", {"username": self.user.email, "password": "prototype-password-1"},
            REMOTE_ADDR="10.0.0.9",
        )
        self.client.logout()
        response = self.client.post(
            "/sign-in/", {"username": "another@iium.edu.my", "password": "x"},
            REMOTE_ADDR="10.0.0.9",
        )
        self.assertEqual(response.status_code, 429)

    def test_registration_is_rate_limited(self):
        for i in range(LIMITS["register"].attempts):
            self.client.post("/register/", dict(REGISTRATION, email=f"a{i}@iium.edu.my",
                                                identification_number=f"21170{i}"))
        response = self.client.post("/register/", REGISTRATION)
        self.assertEqual(response.status_code, 429)

    def test_the_verification_endpoint_is_rate_limited(self):
        """The token is the only thing between a guesser and a verified
        account."""
        for _ in range(LIMITS["verify"].attempts):
            self.client.get("/verify/AAA/bbb-ccc/")
        self.assertEqual(self.client.get("/verify/AAA/bbb-ccc/").status_code, 429)

    def test_two_addresses_from_one_machine_still_share_the_ip_bucket(self):
        """Otherwise one machine simply rotates the address it tries."""
        for i in range(LIMITS["login"].attempts):
            self.client.post("/sign-in/", {"username": f"x{i}@iium.edu.my", "password": "x"})
        response = self.client.post(
            "/sign-in/", {"username": "brand-new@iium.edu.my", "password": "x"}
        )
        self.assertEqual(response.status_code, 429)


class AuthorisationMatrixTests(TestCase):
    """Every screen, against every role. The point is the whole matrix, not the
    individual cells: a permission check added to one view and forgotten on the
    next is exactly how these leak."""

    @classmethod
    def setUpTestData(cls) -> None:
        SystemSetting.seed()
        cls.user = make_user("user@demo.aikol.test")
        cls.approver = make_user("approver@demo.aikol.test", role=Role.APPROVER)
        cls.admin = make_user("admin@demo.aikol.test", role=Role.ADMINISTRATOR)
        cls.venue = Venue.objects.create(
            code="VEN-1", name="Room", venue_type=Venue.VenueType.SEMINAR,
            location="L1", capacity=10,
        )

    #: view name -> the lowest role that may reach it.
    MATRIX = {
        "resources:manage_venues": "admin",
        "resources:manage_vehicles": "admin",
        "resources:manage_facilities": "admin",
        "administration:dashboard": "admin",
        "administration:users": "admin",
        "administration:settings": "admin",
        "administration:site_content": "admin",
        "administration:audit": "admin",
        "administration:retention": "admin",
        "importexport:data_management": "admin",
        "importexport:export_users": "admin",
        "bookings:keys": "admin",
        "bookings:approvals": "approver",
        "reporting:reports": "approver",
        "importexport:export_bookings": "approver",
    }

    def test_the_matrix_holds(self):
        people = {"user": self.user, "approver": self.approver, "admin": self.admin}
        rank = {"user": 0, "approver": 1, "admin": 2}
        for view, needed in self.MATRIX.items():
            for label, person in people.items():
                with self.subTest(view=view, role=label):
                    self.client.force_login(person)
                    response = self.client.get(reverse(view))
                    allowed = rank[label] >= rank[needed]
                    if allowed:
                        self.assertIn(response.status_code, (200, 302),
                                      f"{label} should reach {view}")
                    else:
                        self.assertEqual(response.status_code, 403,
                                         f"{label} must NOT reach {view}")

    def test_an_anonymous_visitor_reaches_none_of_them(self):
        for view in self.MATRIX:
            with self.subTest(view=view):
                response = self.client.get(reverse(view))
                self.assertIn(response.status_code, (302, 403))


class OwnershipTests(TestCase):
    """Ownership is checked on the object, never inferred from the URL."""

    def setUp(self) -> None:
        SystemSetting.seed()
        self.owner = make_user("owner@demo.aikol.test")
        self.other = make_user("other@demo.aikol.test")
        venue = Venue.objects.create(
            code="VEN-1", name="Room", venue_type=Venue.VenueType.SEMINAR,
            location="L1", capacity=10,
        )
        self.booking = Booking.objects.create(
            resource=venue, user=self.owner, created_by=self.owner,
            start_at=timezone.now() + dt.timedelta(days=9),
            end_at=timezone.now() + dt.timedelta(days=9, hours=2),
            purpose="Private", status=BookingStatus.APPROVED,
        )

    def test_somebody_else_cannot_read_it(self):
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(reverse("bookings:detail", args=[self.booking.pk])).status_code, 403
        )

    def test_somebody_else_cannot_cancel_it(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse("bookings:cancel", args=[self.booking.pk]),
            {"reason": "Not mine to cancel"},
        )
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.APPROVED)


class TransportAndHeaderTests(TestCase):
    def test_every_form_carries_a_csrf_token(self):
        self.client.force_login(make_user("person@demo.aikol.test"))
        for url in ("/register/", "/sign-in/", "/password-reset/"):
            with self.subTest(url=url):
                self.client.logout()
                html = self.client.get(url).content.decode()
                self.assertIn("csrfmiddlewaretoken", html)

    def test_user_supplied_text_is_escaped_not_rendered(self):
        """Auto-escaping, checked rather than assumed."""
        SystemSetting.seed()
        person = make_user("xss@demo.aikol.test")
        venue = Venue.objects.create(
            code="VEN-X", name="<script>alert(1)</script>",
            venue_type=Venue.VenueType.SEMINAR, location="L1", capacity=10,
        )
        Booking.objects.create(
            resource=venue, user=person, created_by=person,
            start_at=timezone.now() + dt.timedelta(days=5),
            end_at=timezone.now() + dt.timedelta(days=5, hours=1),
            purpose="<img src=x onerror=alert(1)>", status=BookingStatus.APPROVED,
        )
        self.client.force_login(person)
        html = self.client.get(reverse("bookings:mine")).content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x onerror", html)
        self.assertIn("&lt;script&gt;", html)

    @override_settings(
        SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000, X_FRAME_OPTIONS="DENY",
        SECURE_CONTENT_TYPE_NOSNIFF=True, DEBUG=False,
        ALLOWED_HOSTS=["booking.example.my"],
    )
    def test_the_production_hardening_settings_pass_djangos_own_check(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("check", "--deploy", stdout=out, stderr=out)
        report = out.getvalue()
        for code in ("W004", "W008", "W012", "W016", "W019", "W018"):
            self.assertNotIn(code, report, f"{code} raised: {report}")


class PersonalDataTests(TestCase):
    """Matriculation numbers, telephone numbers and licence numbers are personal
    data. They belong where the purpose requires them and nowhere else."""

    def setUp(self) -> None:
        SystemSetting.seed()
        self.admin = make_user("admin@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.person = make_user(
            "person@demo.aikol.test", affiliation=Affiliation.LECTURER,
        )
        self.person.identification_number = "STAFF-9001"
        self.person.licence_number = "D1234567"
        self.person.licence_expiry = timezone.localdate() + dt.timedelta(days=400)
        self.person.save()

    def test_the_audit_log_free_text_carries_no_identifiers(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("administration:user_edit", args=[self.person.pk]),
            {
                "full_name": self.person.full_name, "email": self.person.email,
                "identification_number": "STAFF-9001", "phone": self.person.phone,
                "affiliation": self.person.affiliation, "role": self.person.role,
                "is_active": "on", "email_verified": "on",
            },
        )
        for entry in AuditLog.objects.all():
            with self.subTest(action=entry.action):
                self.assertNotIn("STAFF-9001", entry.description)
                self.assertNotIn("012-345 6789", entry.description)
                self.assertNotIn("D1234567", entry.description)

    def test_no_email_body_carries_a_licence_number(self):
        for row in EmailOutbox.objects.all():
            self.assertNotIn("D1234567", row.body)

    def test_a_password_hash_never_reaches_a_template(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("administration:user_edit",
                                       args=[self.person.pk])).content.decode()
        self.assertNotIn("pbkdf2", html)
