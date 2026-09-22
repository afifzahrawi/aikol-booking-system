import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.administration.models import SystemSetting
from apps.bookings.keys import issue_key
from apps.bookings.models import (
    AcademicTerm,
    Booking,
    BookingStatus,
    DriverArrangement,
    ManagementDecision,
    TermBreak,
)
from apps.bookings.services import approve_booking
from apps.notifications.models import EmailOutbox
from apps.resources.models import Vehicle, Venue

from .test_conflicts import at


def make_user(email, *, role=Role.USER, verified=True):
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name=email.split("@")[0].replace(".", " ").title(),
        phone="03-6196 4000",
        affiliation=Affiliation.STAFF,
        role=role,
        email_verified=verified,
    )


class OperationalFixtures(TestCase):
    def setUp(self):
        SystemSetting.seed()
        self.admin = make_user("office@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.approver = make_user("approver@demo.aikol.test", role=Role.APPROVER)
        self.requester = make_user("requester@demo.aikol.test")
        self.room = Venue.objects.create(
            code="ROOM-OPS",
            name="Operations Room",
            venue_type=Venue.VenueType.MEETING,
            location="Level 1",
            capacity=30,
        )
        self.car = Vehicle.objects.create(
            code="CAR-OPS",
            name="Operations Car",
            registration_number="WOP 1001",
            make="Proton",
            model="Saga",
            year=2024,
            seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=300),
        )
        self.day = timezone.localdate() + dt.timedelta(days=14)

    def vehicle_booking(self, *, status=BookingStatus.PENDING):
        return Booking.objects.create(
            resource=self.car,
            user=self.requester,
            created_by=self.requester,
            start_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(8))),
            end_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(17))),
            purpose="Official visit",
            passengers=3,
            location_from="AIKOL",
            location_to="Putrajaya",
            driver_arrangement=DriverArrangement.VMU_DRIVER,
            management_status=ManagementDecision.PENDING,
            status=status,
        )


class VehicleManagementWorkflowTests(OperationalFixtures):
    def test_management_approval_assigns_the_driver_and_emails_the_requester(self):
        booking = self.vehicle_booking()
        approve_booking(booking, decided_by=self.approver)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("bookings:vehicle_management", args=[booking.pk]),
            {
                "driver_name": "VMU Driver One",
                "driver_contact": "012-345 6789",
                "reason": "Approved for the official programme.",
                "action": "approve",
            },
        )
        self.assertRedirects(response, reverse("bookings:manage"))
        booking.refresh_from_db()
        self.assertEqual(booking.management_status, ManagementDecision.APPROVED)
        self.assertEqual(booking.driver_name, "VMU Driver One")
        self.assertEqual(booking.management_decided_by, self.admin)
        self.assertTrue(booking.is_fully_approved)
        self.assertTrue(
            EmailOutbox.objects.filter(kind="VEHICLE_MANAGEMENT_APPROVED").exists()
        )

    def test_management_rejection_releases_the_vehicle(self):
        booking = self.vehicle_booking()
        approve_booking(booking, decided_by=self.approver)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("bookings:vehicle_management", args=[booking.pk]),
            {"reason": "The trip is not authorised.", "action": "reject"},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.management_status, ManagementDecision.REJECTED)
        self.assertEqual(booking.status, BookingStatus.REJECTED)
        self.assertTrue(
            EmailOutbox.objects.filter(kind="VEHICLE_MANAGEMENT_REJECTED").exists()
        )

    def test_a_vehicle_key_waits_for_the_second_approval(self):
        booking = self.vehicle_booking(status=BookingStatus.APPROVED)
        with self.assertRaisesMessage(ValidationError, "still needs Kulliyyah management"):
            issue_key(booking, issued_by=self.admin, collected_by_name="Collector")

    def test_only_an_administrator_records_the_management_decision(self):
        booking = self.vehicle_booking(status=BookingStatus.APPROVED)
        self.client.force_login(self.approver)
        self.assertEqual(
            self.client.get(reverse("bookings:vehicle_management", args=[booking.pk])).status_code,
            403,
        )


class AdministratorBookingWorkspaceTests(OperationalFixtures):
    def test_the_booking_register_has_separate_room_and_car_views(self):
        self.vehicle_booking()
        self.client.force_login(self.admin)
        rooms = self.client.get(reverse("bookings:manage"), {"kind": "VENUE"})
        cars = self.client.get(reverse("bookings:manage"), {"kind": "VEHICLE"})
        self.assertContains(rooms, "Venues")
        self.assertNotContains(rooms, self.car.name)
        self.assertContains(cars, self.car.name)

    def test_awaiting_decision_keeps_the_booking_tabs_and_active_state(self):
        self.vehicle_booking()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("bookings:approvals"))
        self.assertContains(response, 'aria-label="Booking resource type"')
        self.assertContains(response, 'aria-current="page">Awaiting Decision</a>')
        self.assertContains(response, f'{reverse("bookings:manage")}?kind=VENUE')

    def test_the_booking_register_has_twenty_rows_and_numbered_pages(self):
        for offset in range(21):
            Booking.objects.create(
                resource=self.room,
                user=self.requester,
                created_by=self.requester,
                start_at=at(self.day + dt.timedelta(days=offset), "09:00"),
                end_at=at(self.day + dt.timedelta(days=offset), "10:00"),
                purpose=f"Booking {offset}",
                status=BookingStatus.APPROVED,
            )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("bookings:manage"), {"kind": "VENUE"})
        self.assertEqual(len(response.context["page"].object_list), 20)
        self.assertEqual(response.context["page"].paginator.num_pages, 2)
        self.assertContains(response, "page=2")

    def test_account_search_is_server_backed_and_administrator_only(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("bookings:user_search"), {"q": "request"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], self.requester.pk)
        self.client.force_login(self.requester)
        self.assertEqual(
            self.client.get(reverse("bookings:user_search"), {"q": "request"}).status_code,
            403,
        )

    def test_the_person_search_and_its_hidden_field_share_one_form(self):
        """user-combobox.js finds the hidden `on_behalf_of` input through the
        form that contains the search box. If either moves out of that form the
        search silently does nothing — which is how it shipped once."""
        self.client.force_login(self.admin)
        html = self.client.get(reverse("bookings:admin_create", args=[self.room.pk])).content.decode()
        at = html.find("data-user-combobox")
        self.assertGreater(at, 0, "the person search is on the page")
        holder = html[html.rfind("<form", 0, at):html.find("</form>", at)]
        self.assertRegex(holder, r'<input[^>]*name="on_behalf_of"[^>]*>')
        self.assertRegex(holder, r'<input[^>]*name="on_behalf_of"[^>]*type="hidden"|<input[^>]*type="hidden"[^>]*name="on_behalf_of"')

    def test_an_administrator_creates_a_series_for_another_user(self):
        term = AcademicTerm.objects.create(
            name="Future semester",
            start_date=self.day,
            end_date=self.day + dt.timedelta(days=40),
        )
        weekday = self.day.weekday()
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("bookings:admin_series_create", args=[self.room.pk]),
            {
                "term": term.pk,
                "starts_on": self.day.isoformat(),
                "repeat_until": (self.day + dt.timedelta(days=21)).isoformat(),
                "purpose": "Weekly class",
                f"day_{weekday}": "on",
                f"from_{weekday}": "10:00",
                f"to_{weekday}": "12:00",
                "on_behalf_of": self.requester.pk,
            },
        )
        self.assertRedirects(response, reverse("bookings:manage"))
        created = Booking.objects.order_by("start_at").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.user, self.requester)
        self.assertEqual(created.created_by, self.admin)


class AcademicCalendarScreenTests(OperationalFixtures):
    def test_an_administrator_can_create_multiple_terms_with_breaks(self):
        self.client.force_login(self.admin)
        for index in range(2):
            start = self.day + dt.timedelta(days=index * 80)
            response = self.client.post(
                reverse("bookings:academic_term_new"),
                {
                    "name": f"Semester {index + 1}",
                    "start_date": start.isoformat(),
                    "end_date": (start + dt.timedelta(days=60)).isoformat(),
                    "breaks-TOTAL_FORMS": "1",
                    "breaks-INITIAL_FORMS": "0",
                    "breaks-MIN_NUM_FORMS": "0",
                    "breaks-MAX_NUM_FORMS": "1000",
                    "breaks-0-name": "Mid-semester break",
                    "breaks-0-start_date": (start + dt.timedelta(days=25)).isoformat(),
                    "breaks-0-end_date": (start + dt.timedelta(days=30)).isoformat(),
                },
            )
            self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        self.assertEqual(AcademicTerm.objects.count(), 2)
        self.assertEqual(TermBreak.objects.count(), 2)

    def test_an_ordinary_user_cannot_manage_calendars(self):
        self.client.force_login(self.requester)
        self.assertEqual(self.client.get(reverse("bookings:academic_terms")).status_code, 403)


class AvailabilityHandoffTests(OperationalFixtures):
    def test_the_chosen_slot_travels_from_the_chart_to_the_form(self):
        """A time typed on the availability page reaches every Book link, and
        the booking form opens with the slot filled in."""
        self.client.force_login(self.requester)
        page = self.client.get(
            reverse("bookings:availability", args=[self.room.pk]),
            {"date": self.day.isoformat(), "start_time": "10:00", "end_time": "12:00"},
        )
        create = reverse("bookings:create", args=[self.room.pk])
        self.assertContains(page, f"{create}?start_date={self.day.isoformat()}&amp;start_time=10:00&amp;end_time=12:00")
        form = self.client.get(create, {"start_date": self.day.isoformat(), "start_time": "10:00", "end_time": "12:00"})
        self.assertContains(form, f'value="{self.day.isoformat()}"')
        self.assertContains(form, 'value="10:00"')
        self.assertContains(form, 'value="12:00"')

    def test_a_malformed_time_is_dropped_not_echoed(self):
        self.client.force_login(self.requester)
        page = self.client.get(
            reverse("bookings:availability", args=[self.room.pk]),
            {"date": self.day.isoformat(), "start_time": "<b>x</b>"},
        )
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "start_time=&lt;b")
        self.assertNotContains(page, "start_time=<b")


class PersonDescriptionTests(OperationalFixtures):
    def test_an_iium_member_without_a_number_is_not_called_public(self):
        """A missing matriculation number once printed "Public account" beside
        an @iium.edu.my address. Affiliation says what a person is; the number
        is shown only when the office holds one."""
        person = self.requester
        person.identification_number = None
        person.affiliation = Affiliation.STAFF
        person.save(update_fields=["identification_number", "affiliation"])
        self.client.force_login(self.admin)
        results = self.client.get(
            reverse("bookings:user_search"), {"q": person.full_name[:6]}
        ).json()["results"]
        meta = next(row["meta"] for row in results if row["id"] == person.pk)
        self.assertEqual(meta, f"{person.email}, Staff")
        self.assertNotIn("Public", meta)

    def test_a_member_of_the_public_is_named_as_one(self):
        person = self.requester
        person.affiliation = Affiliation.PUBLIC
        person.identification_number = None
        person.save(update_fields=["affiliation", "identification_number"])
        self.client.force_login(self.admin)
        results = self.client.get(
            reverse("bookings:user_search"), {"q": person.full_name[:6]}
        ).json()["results"]
        self.assertIn("Member of the public", next(row["meta"] for row in results if row["id"] == person.pk))


class BookingFormLayoutTests(OperationalFixtures):
    def test_a_room_asks_for_one_date_and_a_pair_of_times(self):
        self.client.force_login(self.requester)
        html = self.client.get(reverse("bookings:create", args=[self.room.pk])).content.decode()
        self.assertIn(">Date</label>", html)
        self.assertNotIn(">Start Date</label>", html)
        self.assertNotIn('name="end_date"', html)
        row = html[html.index('name="start_time"'):html.index('name="purpose"')]
        self.assertIn('name="end_time"', row)

    def test_a_vehicle_still_asks_for_both_dates(self):
        self.client.force_login(self.requester)
        html = self.client.get(reverse("bookings:create", args=[self.car.pk])).content.decode()
        self.assertIn(">Start Date</label>", html)
        self.assertIn('name="end_date"', html)
