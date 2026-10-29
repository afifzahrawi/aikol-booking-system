"""The Insights screen: periods, comparisons and the figures on each tab."""

from __future__ import annotations

import datetime as dt

from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.administration.models import SystemSetting
from apps.bookings.models import AcademicTerm, Booking, BookingStatus
from apps.reporting import services
from apps.resources.models import Vehicle, Venue


def make_user(email: str, **extra) -> User:
    return User.objects.create_user(
        email=email, password="prototype-password-1",
        full_name=email.split("@")[0], phone="012-345 6789", email_verified=True, **extra,
    )


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))


def one_day(day: dt.date) -> services.Period:
    period = services.Period("custom", day, day, "One day")
    period.previous = services.Period("previous", day - dt.timedelta(days=1),
                                      day - dt.timedelta(days=1), "Day before")
    return period


class PeriodTests(TestCase):
    today = dt.date(2026, 10, 29)

    def resolve(self, query: str, terms=None):
        terms = terms if terms is not None else services.started_terms(self.today)
        return services.resolve_period(QueryDict(query), self.today, terms)

    def test_the_semester_runs_to_today_and_compares_with_as_much_of_the_last(self):
        AcademicTerm.objects.create(name="Sem 3", start_date=dt.date(2026, 6, 1),
                                    end_date=dt.date(2026, 8, 31))
        AcademicTerm.objects.create(name="Sem 1", start_date=dt.date(2026, 10, 1),
                                    end_date=dt.date(2027, 1, 24))
        period = self.resolve("")
        self.assertEqual((period.kind, period.start, period.end),
                         ("semester", dt.date(2026, 10, 1), self.today))
        self.assertEqual(period.previous.start, dt.date(2026, 6, 1))
        self.assertEqual(period.previous.days, period.days)

    def test_with_no_semester_the_page_shows_the_last_12_months(self):
        period = self.resolve("", terms=[])
        self.assertEqual(period.kind, "year")
        self.assertEqual(period.days, 365)
        self.assertEqual(period.previous.end, period.start - dt.timedelta(days=1))

    def test_this_month_compares_with_the_same_days_of_last_month(self):
        period = self.resolve("period=month")
        self.assertEqual(period.start, dt.date(2026, 10, 1))
        self.assertEqual((period.previous.start, period.previous.end),
                         (dt.date(2026, 9, 1), dt.date(2026, 9, 29)))

    def test_custom_dates_stop_at_today_and_bad_ones_fall_back(self):
        period = self.resolve("period=custom&from=2026-10-01&to=2027-05-01")
        self.assertEqual(period.end, self.today)
        self.assertEqual(self.resolve("period=custom&from=nonsense", terms=[]).kind, "year")


class CompareTests(TestCase):
    def test_wording_and_tone(self):
        self.assertEqual(services.compare(12, 10, label="last month")["text"],
                         "Up 20% on last month")
        self.assertEqual(services.compare(5, 8, unit="hours", higher_is_good=False)["tone"],
                         "good")
        self.assertEqual(services.compare(40, 36, unit="percent_points")["text"], "Up 4 points")
        self.assertEqual(services.compare(3, 3, label="last month")["text"],
                         "Same as last month")

    def test_long_waits_read_in_days(self):
        self.assertEqual(services.duration(6.5), "6.5 h")
        self.assertEqual(services.duration(312.5), "13 days")


class FigureTests(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        self.admin = make_user("admin@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.student = make_user("student@demo.aikol.test")
        self.venue = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type_id=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=40, opens_at=dt.time(8), closes_at=dt.time(18),
        )
        self.car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1",
            make="P", model="B", year=2022, seats=5,
            road_tax_expiry=timezone.localdate() - dt.timedelta(days=2),
        )
        self.day = timezone.localdate() - dt.timedelta(days=3)

    def book(self, resource, start, end, **extra) -> Booking:
        extra.setdefault("status", BookingStatus.APPROVED)
        return Booking.objects.create(
            resource=resource, user=self.student, created_by=self.student,
            start_at=start, end_at=end, purpose="Tutorial", **extra,
        )

    def test_room_use_is_measured_against_the_rooms_own_opening_hours(self):
        """Five hours in a room open ten is half, not five fourteenths."""
        self.book(self.venue, at(self.day, 9), at(self.day, 14), attendees=8)
        use = services.venue_use(one_day(self.day), services.active_venues())
        self.assertEqual(use["rooms"][0]["percent"], 50)
        self.assertEqual(use["fit"][0]["verdict"], "Often too big")

    def test_self_entered_bookings_do_not_count_as_decisions(self):
        decided = at(self.day, 12)
        self.book(self.venue, at(self.day, 9), at(self.day, 10), decided_by=self.admin,
                  decided_at=decided)
        self.book(self.venue, at(self.day, 10), at(self.day, 11), status=BookingStatus.REJECTED,
                  decided_by=self.admin, decided_at=decided, decision_reason="Room needed.")
        own = self.book(self.venue, at(self.day, 11), at(self.day, 12),
                        decided_by=self.admin, decided_at=decided)
        own.created_by = self.admin
        own.save()
        work = services.office_work(one_day(self.day))
        self.assertEqual(work["decided"], 2)
        self.assertEqual(work["reasons"][0]["name"], "Room needed")
        approved = next(k for k in services.kpis(one_day(self.day), [self.venue])
                        if k["title"] == "Approved")
        self.assertEqual(approved["value"], 50)

    def test_a_cancellation_inside_three_days_is_late(self):
        when = timezone.now()
        self.book(self.venue, when + dt.timedelta(days=1), when + dt.timedelta(days=1, hours=1),
                  status=BookingStatus.CANCELLED, cancelled_at=when)
        self.book(self.venue, when + dt.timedelta(days=9), when + dt.timedelta(days=9, hours=1),
                  status=BookingStatus.CANCELLED, cancelled_at=when)
        work = services.office_work(one_day(timezone.localdate()))
        self.assertEqual((work["cancellations"]["early"], work["cancellations"]["late"]), (1, 1))

    def test_destinations_typed_differently_are_one_place(self):
        for where in ("Putrajaya", " putrajaya ", "Melaka"):
            self.book(self.car, at(self.day, 8), at(self.day, 9), location_to=where)
        places = services.vehicle_use(one_day(self.day), [self.car])["places"]
        self.assertEqual((places[0]["name"], places[0]["count"]), ("Putrajaya", 2))

    def test_attention_lists_waiting_requests_and_expired_road_tax(self):
        self.book(self.venue, at(self.day, 9), at(self.day, 10), status=BookingStatus.PENDING)
        items = services.attention([self.car], timezone.localdate())
        self.assertIn("awaiting a decision", items[0]["text"])
        self.assertEqual(items[-1]["tone"], "red")
        self.assertIn("expired 2 days ago", items[-1]["text"])

    def test_the_page_renders_every_tab_and_the_csv_follows_the_period(self):
        self.book(self.venue, at(self.day, 9), at(self.day, 12), attendees=30)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reporting:reports"), {"period": "month",
                                                                   "tab": "office"})
        self.assertEqual(response.status_code, 200)
        for heading in ("Busiest Times", "Each Car", "Time to Decide", "Bookings by Group"):
            self.assertContains(response, heading)
        start = timezone.localdate().replace(day=1)
        self.assertContains(response, f"from={start:%Y-%m-%d}&amp;to=")
        self.assertContains(response, 'data-pane-body="office" >')
