"""The office calendar, the kiosk's short numbers, the room picker and the home page."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from apps.bookings import calendar as cal
from apps.bookings.models import Booking, BookingStatus

from .test_conflicts import at
from .test_kiosk_keys import VehicleFixtures


class CalendarTests(VehicleFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.admin)
        self.url = reverse("bookings:calendar")
        self.week = {"week": self.day.isoformat()}

    def test_the_week_shows_venues_and_vehicles(self):
        page = self.client.get(self.url, self.week)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'data-peek="{self.booking.pk}"')
        self.assertContains(page, f'id="peek-{self.booking.pk}"')

    def test_unticking_vehicles_hides_them(self):
        later = {"week": (self.day + dt.timedelta(days=1)).isoformat()}
        both = self.client.get(self.url, later)
        self.assertContains(both, f'data-peek="{self.trip.pk}"')
        rooms_only = self.client.get(self.url, {**later, "f": "1", "show": "venue"})
        self.assertNotContains(rooms_only, f'data-peek="{self.trip.pk}"')

    def test_search_narrows_the_board(self):
        page = self.client.get(self.url, {**self.week, "q": "no such thing"})
        self.assertNotContains(page, f'data-peek="{self.booking.pk}"')

    def test_overlapping_bookings_share_the_width(self):
        other = Booking.objects.create(
            resource=self.car, user=self.owner, created_by=self.owner,
            start_at=at(self.day, "11:00"), end_at=at(self.day, "13:00"),
            purpose="Overlap", status=BookingStatus.PENDING,
        )
        board = cal.week(cal.monday_of(self.day), kinds={"venue", "vehicle"})
        day = next(d for d in board["days"] if d.date == self.day)
        blocks = {b.booking.pk: b for b in day.blocks}
        self.assertEqual(blocks[self.booking.pk].lanes, 2)
        self.assertNotEqual(blocks[self.booking.pk].lane, blocks[other.pk].lane)
        self.assertLess(blocks[other.pk].width, 50)

    def test_by_room_lists_each_resource(self):
        page = self.client.get(self.url, {**self.week, "view": "rooms", "day": self.day.isoformat()})
        self.assertContains(page, "Seminar Room 1")
        self.assertContains(page, "Kulliyyah Car")

    def test_approving_from_the_calendar_returns_to_it(self):
        pending = Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=at(self.day, "15:00"), end_at=at(self.day, "16:00"),
            purpose="Meeting", status=BookingStatus.PENDING,
        )
        back = f"{self.url}?week={self.day.isoformat()}"
        response = self.client.post(
            reverse("bookings:decide", args=[pending.pk]),
            {"action": "approve", "reason": "", "next": back},
        )
        self.assertRedirects(response, back, fetch_redirect_response=False)
        pending.refresh_from_db()
        self.assertEqual(pending.status, BookingStatus.APPROVED)

    def test_an_outside_next_is_ignored(self):
        pending = Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=at(self.day, "15:00"), end_at=at(self.day, "16:00"),
            purpose="Meeting", status=BookingStatus.PENDING,
        )
        response = self.client.post(
            reverse("bookings:decide", args=[pending.pk]),
            {"action": "approve", "reason": "", "next": "https://example.com/"},
        )
        self.assertRedirects(response, reverse("bookings:approvals"), fetch_redirect_response=False)

    def test_only_the_admin_sees_the_calendar(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class KioskShortNumberTests(VehicleFixtures):
    def setUp(self) -> None:
        super().setUp()
        today = timezone.localdate()
        # "Today" must still have the booking ahead whatever the hour the
        # suite runs, so the clock is held at 09:00.
        clock = patch("django.utils.timezone.now", return_value=at(today, "09:00"))
        clock.start()
        self.addCleanup(clock.stop)
        self.today_booking = Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=at(today, "21:00"), end_at=at(today, "21:45"),
            purpose="Evening", status=BookingStatus.APPROVED,
        )
        self.client.force_login(self.admin)

    def test_four_digits_find_todays_booking(self):
        digits = self.today_booking.booking_reference[-4:]
        response = self.client.post(reverse("bookings:kiosk"), {"reference": digits})
        self.assertRedirects(
            response,
            reverse("bookings:kiosk_booking", args=[self.today_booking.booking_reference]),
        )

    def test_todays_tiles_show_no_names(self):
        page = self.client.get(reverse("bookings:kiosk"))
        self.assertContains(page, self.today_booking.booking_reference[-4:])
        self.assertNotContains(page, self.owner.full_name)


class RoomPickerAndHomeTests(VehicleFixtures):
    def test_a_room_page_offers_free_and_taken_times(self):
        self.client.force_login(self.plain)
        page = self.client.get(reverse("resources:detail", args=[self.room.pk]))
        self.assertContains(page, "data-picker")
        self.assertContains(page, "disabled")
        car = self.client.get(reverse("resources:detail", args=[self.car.pk]))
        self.assertNotContains(car, "data-picker")

    def test_up_next_shows_progress(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(page, "Up Next")
        self.assertContains(page, "Seminar Room 1")
        self.assertEqual(page.context["next_step"], 2)
