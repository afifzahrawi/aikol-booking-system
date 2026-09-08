"""Every URL, rendered.

A view can pass its own unit tests and still fail to render: a missing
`{% load static %}`, a filter applied to the wrong type, a `{% url %}` naming a
route that moved. This walks the whole URL map so that class of fault cannot
reach a deployment.

It also asserts the two things a template can silently get wrong and no other
test would notice: that the stylesheet is linked, and that no page leaks a
server error page instead of content.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.administration.models import SystemSetting
from apps.bookings.models import AcademicTerm, Booking, BookingStatus, KeyHandover
from apps.resources.models import Facility, Vehicle, Venue


class SmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        SystemSetting.seed()
        cls.admin = User.objects.create_user(
            email="admin@demo.aikol.test", password="prototype-password-1",
            full_name="Admin", phone="03-6196 4000", email_verified=True,
            role=Role.ADMINISTRATOR, affiliation=Affiliation.STAFF,
        )
        cls.venue = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        cls.car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1",
            make="Perodua", model="Bezza", year=2023, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=300),
        )
        cls.facility = Facility.objects.create(
            code="projector", name="Projector", applies_to="VENUE"
        )
        today = timezone.localdate()
        AcademicTerm.objects.create(
            name="Semester 1", start_date=today - dt.timedelta(days=10),
            end_date=today + dt.timedelta(days=80),
        )
        cls.booking = Booking.objects.create(
            resource=cls.venue, user=cls.admin, created_by=cls.admin,
            start_at=timezone.now() + dt.timedelta(days=5),
            end_at=timezone.now() + dt.timedelta(days=5, hours=2),
            purpose="Tutorial", status=BookingStatus.APPROVED,
        )
        KeyHandover.objects.create(
            booking=cls.booking, issued_at=timezone.now(), issued_by=cls.admin,
            collected_by_name="Aiman",
        )

    #: Pages for somebody who is signed out. `/sign-in/` deliberately redirects
    #: an authenticated visitor, so it cannot be walked with the others.
    ANONYMOUS = (
        "accounts:login",
        "accounts:register",
        "accounts:register_done",
        "accounts:password_reset",
        "accounts:password_reset_done",
    )

    def pages(self) -> list[str]:
        return [
            reverse("accounts:dashboard"),
            reverse("resources:venues"),
            reverse("resources:vehicles"),
            reverse("resources:detail", args=[self.venue.pk]),
            reverse("resources:detail", args=[self.car.pk]),
            reverse("resources:manage_venues"),
            reverse("resources:manage_vehicles"),
            reverse("resources:manage_facilities"),
            reverse("resources:venue_new"),
            reverse("resources:vehicle_new"),
            reverse("resources:venue_edit", args=[self.venue.pk]),
            reverse("resources:vehicle_edit", args=[self.car.pk]),
            reverse("resources:facility_new"),
            reverse("resources:facility_edit", args=[self.facility.pk]),
            reverse("resources:images", args=[self.venue.pk]),
            reverse("resources:delete", args=[self.venue.pk]),
            reverse("bookings:mine"),
            reverse("bookings:detail", args=[self.booking.pk]),
            reverse("bookings:cancel", args=[self.booking.pk]),
            reverse("bookings:availability", args=[self.venue.pk]),
            reverse("bookings:create", args=[self.venue.pk]),
            reverse("bookings:create", args=[self.car.pk]),
            reverse("bookings:series_create", args=[self.venue.pk]),
            reverse("bookings:approvals"),
            reverse("bookings:keys"),
            reverse("bookings:key_issue", args=[self.booking.pk]),
            reverse("bookings:key_return", args=[self.booking.pk]),
            reverse("administration:dashboard"),
            reverse("administration:users"),
            reverse("administration:user_edit", args=[self.admin.pk]),
            reverse("administration:settings"),
            reverse("administration:site_content"),
            reverse("administration:audit"),
            reverse("administration:retention"),
            reverse("reporting:reports"),
            reverse("importexport:data_management"),
        ]

    def test_every_page_renders_for_an_administrator(self):
        self.client.force_login(self.admin)
        for url in self.pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, f"{url} did not render")

    def test_every_page_links_the_stylesheet(self):
        """A page that renders without its stylesheet still looks broken."""
        self.client.force_login(self.admin)
        for url in self.pages():
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                if "app.css" not in html:
                    self.fail(f"{url} does not link the stylesheet")

    def test_a_pending_decision_page_renders(self):
        pending = Booking.objects.create(
            resource=self.venue, user=self.admin, created_by=self.admin,
            start_at=timezone.now() + dt.timedelta(days=9),
            end_at=timezone.now() + dt.timedelta(days=9, hours=2),
            purpose="Awaiting", status=BookingStatus.PENDING,
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("bookings:decide", args=[pending.pk])).status_code, 200
        )

    def test_a_series_decision_page_renders(self):
        from apps.bookings.models import BookingSeries

        series = BookingSeries.objects.create(
            resource=self.venue, user=self.admin, weekday_times={"0": ["09:00", "11:00"]},
            starts_on=timezone.localdate(), repeat_until=timezone.localdate(),
            purpose="Weekly",
        )
        self.client.force_login(self.admin)
        for name in ("bookings:decide_series", "bookings:series_cancel"):
            with self.subTest(view=name):
                self.assertEqual(
                    self.client.get(reverse(name, args=[series.pk])).status_code, 200
                )

    def test_every_signed_out_page_renders(self):
        for name in self.ANONYMOUS:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn("app.css", response.content.decode())

    def test_sign_in_sends_an_authenticated_visitor_onward(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 302)

    def test_a_signed_out_visitor_is_never_shown_a_server_error(self):
        """Anonymous access should redirect or refuse, never crash."""
        for url in self.pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(
                    response.status_code, (200, 302, 403), f"{url} returned {response.status_code}"
                )
