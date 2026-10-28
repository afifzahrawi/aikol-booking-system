"""The venue and vehicle picker, and the buildings that group it."""

from __future__ import annotations

import datetime as dt

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.bookings.models import Booking, BookingStatus
from apps.resources.models import Building, Venue

from .test_management import Fixtures, make_user


def at(day: dt.date, clock: str) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time.fromisoformat(clock)))


class PickerTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.day = timezone.localdate() + dt.timedelta(days=14)
        self.small = Venue.objects.create(
            code="VEN-2", name="Discussion Room", venue_type_id=Venue.VenueType.DISCUSSION,
            location="Level 1, AIKOL Library Wing", capacity=12,
        )
        self.client.force_login(self.plain)

    def query(self, **extra) -> dict:
        params = {"date": self.day.isoformat(), "from": "09:00", "until": "11:00", "free": "0"}
        params.update(extra)
        return params

    def picks(self, response) -> dict[str, str]:
        return {
            pick.resource.name: pick.state
            for group in response.context["groups"]
            for pick in group.picks
        }

    def test_a_booked_room_is_marked_busy_and_hidden_when_only_free_rooms_are_asked_for(self):
        Booking.objects.create(
            resource=self.small, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"),
            purpose="Fixture", status=BookingStatus.PENDING,
        )
        response = self.client.get(reverse("resources:venues"), self.query())
        self.assertEqual(self.picks(response)["Discussion Room"], "busy")
        self.assertContains(response, "Booked until 12:00")

        response = self.client.get(reverse("resources:venues"), self.query(free="1"))
        self.assertNotIn("Discussion Room", self.picks(response))

    def test_adjacent_bookings_leave_the_room_free(self):
        Booking.objects.create(
            resource=self.small, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "11:00"), end_at=at(self.day, "12:00"),
            purpose="Fixture", status=BookingStatus.APPROVED,
        )
        response = self.client.get(reverse("resources:venues"), self.query())
        self.assertEqual(self.picks(response)["Discussion Room"], "free")

    def test_people_puts_the_smallest_room_that_fits_first(self):
        Venue.objects.create(
            code="VEN-3", name="Seminar Room", venue_type_id=Venue.VenueType.SEMINAR,
            location="Level 1, AIKOL Library Wing", capacity=30,
        )
        response = self.client.get(reverse("resources:venues"), self.query(people="20"))
        names = list(self.picks(response))
        self.assertNotIn("Discussion Room", names)
        self.assertEqual(names[0], "Seminar Room")
        self.assertContains(response, "Best fit")

    def test_venues_are_grouped_by_building(self):
        response = self.client.get(reverse("resources:venues"), self.query())
        self.assertEqual(
            sorted(group.name for group in response.context["groups"]),
            ["AIKOL Library Wing", "Level 2"],
        )

    def test_free_rooms_offer_a_booking_link_with_the_chosen_time(self):
        response = self.client.get(reverse("resources:venues"), self.query())
        self.assertContains(
            response,
            f"/resource/{self.small.pk}/book/?start_date={self.day:%Y-%m-%d}"
            "&amp;start_time=09:00",
        )

    def test_recent_rooms_come_from_the_persons_own_bookings(self):
        Booking.objects.create(
            resource=self.small, user=self.plain, created_by=self.plain,
            start_at=at(self.day + dt.timedelta(days=1), "09:00"),
            end_at=at(self.day + dt.timedelta(days=1), "10:00"),
            purpose="Fixture", status=BookingStatus.APPROVED,
        )
        response = self.client.get(reverse("resources:venues"), self.query())
        self.assertEqual([p.resource.name for p in response.context["recent"]], ["Discussion Room"])
        self.client.force_login(self.approver)
        response = self.client.get(reverse("resources:venues"), self.query())
        self.assertEqual(response.context["recent"], [])

    def test_the_script_can_ask_for_the_results_alone(self):
        response = self.client.get(
            reverse("resources:venues"), self.query(), HTTP_X_PICKER="results"
        )
        self.assertNotContains(response, "<html")
        self.assertContains(response, "picker-results")

    def test_a_period_in_the_past_is_explained_not_offered(self):
        past = timezone.localdate() - dt.timedelta(days=2)
        response = self.client.get(reverse("resources:venues"), self.query(date=past.isoformat()))
        self.assertContains(response, "cannot start in the past")
        self.assertNotContains(response, "start_date=")

    def test_vehicles_use_the_same_picker(self):
        response = self.client.get(reverse("resources:vehicles"), self.query())
        self.assertEqual(self.picks(response), {"Kulliyyah Car": "free"})
        self.assertContains(response, "Find a Vehicle")


class BuildingTests(Fixtures):
    def test_a_venue_saved_with_only_a_location_is_put_in_a_building(self):
        venue = Venue.objects.create(
            code="VEN-9", name="Annex Room", venue_type_id=Venue.VenueType.MEETING,
            location="Level 2, AIKOL Annex", capacity=10,
        )
        self.assertEqual(venue.building.name, "AIKOL Annex")
        again = Venue.objects.create(
            code="VEN-10", name="Annex Room 2", venue_type_id=Venue.VenueType.MEETING,
            location="aikol annex", capacity=10,
        )
        self.assertEqual(again.building, venue.building)

    def test_the_admin_can_add_and_rename_a_building(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("resources:building_new"),
            {"name": "Postgraduate Block", "is_active": "True", "display_order": "3"},
        )
        self.assertEqual(response.status_code, 302)
        building = Building.objects.get(name="Postgraduate Block")
        self.client.post(
            reverse("resources:building_edit", args=[building.pk]),
            {"name": "Postgraduate Centre", "is_active": "True", "display_order": "3"},
        )
        building.refresh_from_db()
        self.assertEqual(building.name, "Postgraduate Centre")
        self.assertTrue(AuditLog.objects.filter(action="BUILDING_UPDATED").exists())

    def test_a_building_with_venues_cannot_be_deleted(self):
        self.client.force_login(self.admin)
        building = self.venue.building
        self.client.post(reverse("resources:building_delete", args=[building.pk]))
        self.assertTrue(Building.objects.filter(pk=building.pk).exists())
        empty = Building.objects.create(name="Empty Block")
        self.client.post(reverse("resources:building_delete", args=[empty.pk]))
        self.assertFalse(Building.objects.filter(pk=empty.pk).exists())

    def test_only_the_admin_may_manage_buildings(self):
        for user in (self.plain, make_user("approver2@demo.aikol.test", Role.APPROVER)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("resources:manage_buildings")).status_code, 403)
