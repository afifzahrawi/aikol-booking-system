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

    def test_more_than_two_overlaps_are_counted_not_squeezed(self):
        for hour in ("09:30", "10:00", "10:30"):
            Booking.objects.create(
                resource=self.car, user=self.owner, created_by=self.owner,
                start_at=at(self.day, hour), end_at=at(self.day, "12:00"),
                purpose="Crowded", status=BookingStatus.PENDING,
            )
        board = cal.week(cal.monday_of(self.day), kinds={"venue", "vehicle"})
        day = next(d for d in board["days"] if d.date == self.day)
        self.assertTrue(all(b.lane < cal.MAX_LANES for b in day.blocks))
        self.assertEqual(
            len(day.blocks) + sum(b.hidden for b in day.blocks), len(day.agenda)
        )
        page = self.client.get(self.url, self.week)
        self.assertContains(page, "more</a>")
        self.assertContains(page, f'id="panel-day-{self.day.isoformat()}"')

    def test_a_booking_over_several_days_is_a_trip_not_a_column(self):
        away = Booking.objects.create(
            resource=self.car, user=self.owner, created_by=self.owner,
            start_at=at(self.day + dt.timedelta(days=20), "08:00"),
            end_at=at(self.day + dt.timedelta(days=22), "17:00"),
            purpose="Visit", status=BookingStatus.APPROVED,
        )
        board = cal.week(cal.monday_of(away.start_at.date()), kinds={"vehicle"})
        self.assertEqual([t.booking for t in board["trips"]], [away])
        self.assertFalse(any(b.booking == away for d in board["days"] for b in d.blocks))
        days_listing_it = [d for d in board["days"] if away in d.agenda]
        trip = board["trips"][0]
        self.assertEqual(len(days_listing_it), trip.last - trip.first + 1)

    def test_by_room_groups_rooms_by_building(self):
        board = cal.by_room(self.day, kinds={"venue", "vehicle"})
        names = [g["name"] for g in board["groups"]]
        self.assertEqual(names[-1], cal.VEHICLE_GROUP)
        self.assertEqual(len(names), len(set(names)))

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
        # A booking inside the week the page shows; earlier slots today are only
        # taken once the day has started, so the test must not rely on them.
        tomorrow = timezone.localdate() + dt.timedelta(days=1)
        Booking.objects.create(
            resource=self.room, user=self.owner, created_by=self.owner,
            start_at=at(tomorrow, "10:00"), end_at=at(tomorrow, "11:00"),
            purpose="Taken", status=BookingStatus.APPROVED,
        )
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
