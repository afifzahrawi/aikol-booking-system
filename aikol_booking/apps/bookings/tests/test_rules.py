"""Period rules, driver eligibility and the academic calendar.

The pair that matters most here is the last two duration tests: the limit is
chosen from `resource_type`, and applying the venue rule to a car would make
multi-day trips impossible while every other test still passed.
"""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Affiliation, User
from apps.administration.models import SystemSetting
from apps.bookings.models import AcademicTerm, DriverArrangement, TermBreak
from apps.bookings.services import check_driver_arrangement, expand_series, validate_period
from apps.resources.models import ResourceStatus, Vehicle, Venue

from .test_conflicts import at


def make_user(email: str, affiliation: str, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name=email.split("@")[0].title(),
        phone="03-6196 4000",
        affiliation=affiliation,
        email_verified=True,
        **extra,
    )


class PeriodRuleTests(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        self.day = timezone.localdate() + dt.timedelta(days=10)
        self.venue = Venue.objects.create(
            code="VEN-1", name="Moot Court", venue_type=Venue.VenueType.MOOT_COURT,
            location="Level 2", capacity=80,
        )
        self.car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1111",
            make="Perodua", model="Bezza", year=2023, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=200),
        )

    def test_a_normal_room_booking_is_accepted(self):
        self.assertEqual(validate_period(self.venue, at(self.day, "10:00"), at(self.day, "12:00")), [])

    def test_a_room_booking_over_nine_hours_is_refused(self):
        problems = validate_period(self.venue, at(self.day, "08:00"), at(self.day, "18:00"))
        self.assertTrue(any("may not exceed 9 hours" in p for p in problems))

    def test_a_room_booking_of_exactly_nine_hours_is_accepted(self):
        self.assertEqual(validate_period(self.venue, at(self.day, "08:00"), at(self.day, "17:00")), [])

    def test_a_room_booking_outside_the_window_is_refused(self):
        problems = validate_period(self.venue, at(self.day, "07:00"), at(self.day, "09:00"))
        self.assertTrue(any("bookable between" in p for p in problems))

    def test_a_room_booking_cannot_span_days(self):
        end = at(self.day + dt.timedelta(days=1), "10:00")
        problems = validate_period(self.venue, at(self.day, "20:00"), end)
        self.assertTrue(any("same day" in p for p in problems))

    def test_a_three_day_vehicle_trip_is_accepted(self):
        """The nine-hour venue limit must not be applied to a car."""
        end = at(self.day + dt.timedelta(days=2), "17:00")
        self.assertEqual(validate_period(self.car, at(self.day, "08:00"), end), [])

    def test_a_vehicle_trip_longer_than_the_cap_is_refused(self):
        end = at(self.day + dt.timedelta(days=9), "17:00")
        problems = validate_period(self.car, at(self.day, "08:00"), end)
        self.assertTrue(any("may not exceed 7 days" in p for p in problems))

    def test_a_booking_beyond_the_advance_limit_is_refused(self):
        far = timezone.localdate() + dt.timedelta(days=120)
        problems = validate_period(self.venue, at(far, "10:00"), at(far, "12:00"))
        self.assertTrue(any("90 days ahead" in p for p in problems))

    def test_a_booking_in_the_past_is_refused(self):
        past = timezone.localdate() - dt.timedelta(days=1)
        problems = validate_period(self.venue, at(past, "10:00"), at(past, "12:00"))
        self.assertTrue(any("in the past" in p for p in problems))

    def test_an_untaxed_car_is_withdrawn_without_naming_the_reason(self):
        """You cannot lawfully drive an untaxed car, but the expiry date is an
        office matter. The requester is told the vehicle is unavailable."""
        self.car.road_tax_expiry = timezone.localdate() - dt.timedelta(days=1)
        self.car.save(update_fields=["road_tax_expiry"])
        problems = validate_period(self.car, at(self.day, "08:00"), at(self.day, "17:00"))
        self.assertTrue(any("not available for that period" in p for p in problems))
        joined = " ".join(problems).lower()
        self.assertNotIn("road tax", joined)
        self.assertNotIn(str(self.car.road_tax_expiry.year), joined)

    def test_a_maintenance_resource_is_not_bookable(self):
        self.venue.status = ResourceStatus.MAINTENANCE
        self.venue.save(update_fields=["status"])
        problems = validate_period(self.venue, at(self.day, "10:00"), at(self.day, "12:00"))
        self.assertTrue(any("not available" in p for p in problems))


class DriverEligibilityTests(TestCase):
    """Who may book is not who may drive. Anyone may request a car."""

    def setUp(self) -> None:
        self.car = Vehicle.objects.create(
            code="CAR-2", name="Kulliyyah Car", registration_number="WBB 2222",
            make="Proton", model="Exora", year=2020, seats=7,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=200),
        )

    def test_a_student_may_not_self_drive(self):
        student = make_user("student@demo.aikol.test", Affiliation.STUDENT)
        problems = check_driver_arrangement(student, self.car, DriverArrangement.SELF_DRIVE)
        self.assertTrue(any("Only lecturers and staff may drive" in p for p in problems))

    def test_a_student_requesting_a_vmu_driver_is_told_about_the_second_approval(self):
        student = make_user("student2@demo.aikol.test", Affiliation.STUDENT)
        problems = check_driver_arrangement(student, self.car, DriverArrangement.VMU_DRIVER)
        self.assertTrue(any("management approval" in p for p in problems))
        # It is a notice, not a refusal on eligibility grounds.
        self.assertFalse(any("Only lecturers and staff" in p for p in problems))

    def test_a_lecturer_with_a_licence_may_self_drive(self):
        lecturer = make_user(
            "lecturer@demo.aikol.test",
            Affiliation.LECTURER,
            licence_number="D1234567",
            licence_expiry=timezone.localdate() + dt.timedelta(days=400),
        )
        self.assertEqual(check_driver_arrangement(lecturer, self.car, DriverArrangement.SELF_DRIVE), [])

    def test_self_drive_without_a_licence_on_file_is_refused(self):
        staff = make_user("staff@demo.aikol.test", Affiliation.STAFF)
        problems = check_driver_arrangement(staff, self.car, DriverArrangement.SELF_DRIVE)
        self.assertTrue(any("licence number and expiry" in p for p in problems))

    def test_a_venue_has_no_driver_question_at_all(self):
        venue = Venue.objects.create(
            code="VEN-2", name="Meeting Room", venue_type=Venue.VenueType.MEETING,
            location="Level 1", capacity=12,
        )
        self.assertEqual(check_driver_arrangement(make_user("x@demo.aikol.test", Affiliation.STUDENT),
                                                  venue, DriverArrangement.SELF_DRIVE), [])


class AcademicCalendarTests(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        self.today = timezone.localdate()
        self.term = AcademicTerm.objects.create(
            name="Semester 1, 2026/2027",
            start_date=self.today - dt.timedelta(days=21),
            end_date=self.today + dt.timedelta(days=80),
        )
        TermBreak.objects.create(
            term=self.term,
            name="Mid-semester break",
            start_date=self.today + dt.timedelta(days=28),
            end_date=self.today + dt.timedelta(days=34),
        )

    def test_several_terms_coexist(self):
        AcademicTerm.objects.create(
            name="Semester 2, 2026/2027",
            start_date=self.today + dt.timedelta(days=120),
            end_date=self.today + dt.timedelta(days=220),
        )
        self.assertEqual(AcademicTerm.objects.count(), 2)
        self.assertEqual(AcademicTerm.current(), self.term)

    def test_an_overlapping_term_is_refused_and_names_the_clash(self):
        clash = AcademicTerm(
            name="Overlapping",
            start_date=self.today,
            end_date=self.today + dt.timedelta(days=30),
        )
        with self.assertRaises(ValidationError) as ctx:
            clash.clean()
        self.assertIn(self.term.name, str(ctx.exception))

    def test_a_term_ending_before_it_starts_is_refused(self):
        with self.assertRaises(ValidationError):
            AcademicTerm(
                name="Backwards",
                start_date=self.today + dt.timedelta(days=300),
                end_date=self.today + dt.timedelta(days=290),
            ).clean()

    def test_for_date_finds_the_containing_term(self):
        self.assertEqual(AcademicTerm.for_date(self.today), self.term)

    def test_a_date_between_semesters_belongs_to_none(self):
        self.assertIsNone(AcademicTerm.for_date(self.today + dt.timedelta(days=100)))

    def test_a_teaching_date_carries_a_class(self):
        self.assertEqual(self.term.exclusion_for(self.today + dt.timedelta(days=7)), "")

    def test_a_break_date_is_excluded_by_its_own_name(self):
        self.assertEqual(
            self.term.exclusion_for(self.today + dt.timedelta(days=30)), "mid-semester break"
        )

    def test_dates_outside_teaching_say_which_end(self):
        self.assertEqual(
            self.term.exclusion_for(self.today - dt.timedelta(days=30)),
            "before the semester begins",
        )
        self.assertEqual(
            self.term.exclusion_for(self.today + dt.timedelta(days=200)),
            "after the semester ends",
        )


class SeriesExpansionTests(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        today = timezone.localdate()
        self.term = AcademicTerm.objects.create(
            name="Semester", start_date=today, end_date=today + dt.timedelta(days=90)
        )
        self.monday = today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)

    def test_a_weekly_series_produces_one_occurrence_per_week(self):
        occs = expand_series(
            term=self.term,
            weekday_times={"0": ["09:00", "11:00"]},
            starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=28),
        )
        self.assertEqual(len(occs), 5)
        self.assertTrue(all(o["skip_reason"] == "" for o in occs))

    def test_each_weekday_keeps_its_own_times(self):
        """A course may meet Monday morning and Thursday afternoon. Forcing one
        pair of times on both would be wrong."""
        occs = expand_series(
            term=self.term,
            weekday_times={"0": ["09:00", "11:00"], "3": ["14:00", "16:00"]},
            starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=7),
        )
        by_weekday = {o["date"].weekday(): (o["start_time"], o["end_time"]) for o in occs}
        self.assertEqual(by_weekday[0], (dt.time(9, 0), dt.time(11, 0)))
        self.assertEqual(by_weekday[3], (dt.time(14, 0), dt.time(16, 0)))

    def test_an_occurrence_in_a_break_is_reported_not_dropped(self):
        TermBreak.objects.create(
            term=self.term,
            name="Mid-semester break",
            start_date=self.monday + dt.timedelta(days=7),
            end_date=self.monday + dt.timedelta(days=13),
        )
        occs = expand_series(
            term=self.term,
            weekday_times={"0": ["09:00", "11:00"]},
            starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=21),
        )
        skipped = [o for o in occs if o["skip_reason"]]
        self.assertEqual(len(occs), 4, "the break date is still returned, carrying its reason")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["skip_reason"], "mid-semester break")

    def test_expansion_stops_at_the_configured_cap(self):
        occs = expand_series(
            term=self.term,
            weekday_times={str(d): ["09:00", "10:00"] for d in range(7)},
            starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=365),
        )
        self.assertEqual(len(occs), SystemSetting.get_int("maximum_series_occurrences"))
