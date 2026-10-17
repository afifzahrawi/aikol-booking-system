"""Weekly bookings: several times a day, the audit log, and mid-semester changes."""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.bookings.forms import RecurrenceForm
from apps.bookings.models import Booking, BookingSeries, BookingStatus
from apps.bookings.services import change_series, create_series, expand_series
from apps.resources.models import Venue

from .test_conflicts import at
from .test_workflow import Fixtures


class SeveralTimesADayTests(Fixtures):
    def form(self, **extra):
        data = {
            "term": self.term.pk,
            "starts_on": self.monday.isoformat(),
            "repeat_until": (self.monday + dt.timedelta(days=7)).isoformat(),
            "purpose": "Contract Law",
            "day_0": "on", "from_0": "09:00", "to_0": "11:00",
        }
        data.update(extra)
        return RecurrenceForm(data, user=self.requester)

    def test_a_day_can_hold_two_times(self):
        form = self.form(from_0_2="14:00", to_0_2="16:00")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["weekday_times"], {"0": [["09:00", "11:00"], ["14:00", "16:00"]]}
        )

    def test_times_on_one_day_may_not_overlap(self):
        form = self.form(from_0_2="10:00", to_0_2="12:00")
        self.assertFalse(form.is_valid())
        self.assertIn("overlaps", str(form.errors))

    def test_an_empty_extra_slot_is_ignored(self):
        form = self.form(from_0_2="", to_0_2="")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["weekday_times"], {"0": [["09:00", "11:00"]]})

    def test_each_time_becomes_its_own_booking(self):
        times = {"0": [["09:00", "11:00"], ["14:00", "16:00"]]}
        occurrences = expand_series(
            term=self.term, weekday_times=times, starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=7),
        )
        self.assertEqual(len(occurrences), 4)
        series, created, _ = create_series(
            resource=self.room, user=self.requester, created_by=self.requester,
            term=self.term, weekday_times=times, starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=7), purpose="Lecture and tutorial",
        )
        self.assertEqual(len(created), 4)
        self.assertEqual(
            series.describe_times(), "Mon 09:00 to 11:00 and 14:00 to 16:00"
        )

    def test_an_older_series_still_reads(self):
        self.assertEqual(BookingSeries.slots_for({"3": ["14:00", "16:00"]}, 3), [["14:00", "16:00"]])

    def test_a_weekly_booking_is_written_to_the_audit_log(self):
        self.client.force_login(self.requester)
        data = {
            "term": self.term.pk,
            "starts_on": self.monday.isoformat(),
            "repeat_until": (self.monday + dt.timedelta(days=7)).isoformat(),
            "purpose": "Contract Law",
            "day_0": "on", "from_0": "09:00", "to_0": "11:00",
            "from_0_2": "14:00", "to_0_2": "16:00",
        }
        response = self.client.post(reverse("bookings:series_create", args=[self.room.pk]), data)
        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.get(action="SERIES_CREATED")
        self.assertIn("Seminar Room 1", log.description)
        self.assertIn("14:00 to 16:00", log.description)
        self.assertIn("4 requested", log.description)


class TimetableChangeTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.other_room = Venue.objects.create(
            code="VEN-2", name="Seminar Room 2", venue_type_id=Venue.VenueType.SEMINAR,
            location="Level 2", capacity=30,
        )
        self.series, self.created, _ = create_series(
            resource=self.room, user=self.requester, created_by=self.requester,
            term=self.term, weekday_times={"0": [["09:00", "11:00"]]}, starts_on=self.monday,
            repeat_until=self.monday + dt.timedelta(days=35), purpose="Contract Law",
        )
        self.change_on = self.monday + dt.timedelta(days=21)

    def change(self, **overrides):
        params = {
            "changed_by": self.requester,
            "from_date": self.change_on,
            "resource": self.other_room,
            "weekday_times": {"3": [["14:00", "16:00"]]},
            "repeat_until": self.series.repeat_until,
            "purpose": "Contract Law",
            "reason": "Faculty moved the class",
        }
        params.update(overrides)
        return change_series(self.series, **params)

    def test_dates_before_the_change_stay_and_later_ones_move(self):
        new_series, created, plan, cancelled = self.change()
        old = Booking.objects.filter(series=self.series)
        kept = old.filter(status=BookingStatus.PENDING)
        self.assertTrue(all(b.start_at < at(self.change_on, "00:00") for b in kept))
        self.assertEqual(cancelled, old.filter(status=BookingStatus.CANCELLED).count())
        self.assertGreater(cancelled, 0)
        self.assertIn("Timetable changed", old.filter(status=BookingStatus.CANCELLED)
                      .first().cancellation_reason)
        self.assertEqual(new_series.replaces, self.series)
        self.assertEqual(new_series.resource_id, self.other_room.pk)
        self.assertTrue(all(b.status == BookingStatus.PENDING for b in created))

    def test_the_same_room_at_the_same_time_is_not_a_clash_with_itself(self):
        """Moving only the day keeps the room; the old dates being replaced
        must not count as clashes in the preview or in the change."""
        new_series, created, plan, _ = self.change(
            resource=self.room, weekday_times={"0": [["10:00", "12:00"]]}
        )
        self.assertFalse(plan["clashing"])
        self.assertTrue(created)

    def test_a_clash_leaves_the_old_series_untouched(self):
        thursday = self.change_on + dt.timedelta(days=(3 - self.change_on.weekday()) % 7)
        Booking.objects.create(
            resource=self.other_room, user=self.admin, created_by=self.admin,
            start_at=at(thursday, "14:00"), end_at=at(thursday, "16:00"),
            purpose="Already there", status=BookingStatus.APPROVED,
        )
        with self.assertRaises(ValidationError):
            self.change()
        self.assertFalse(
            Booking.objects.filter(series=self.series, status=BookingStatus.CANCELLED).exists()
        )
        self.assertEqual(BookingSeries.objects.count(), 1)

    def test_a_requester_needs_three_days_notice(self):
        with self.assertRaises(ValidationError):
            self.change(from_date=self.monday.__class__.today())

    def test_only_the_owner_or_the_admin_may_change_it(self):
        other = self.approver
        self.client.force_login(other)
        url = reverse("bookings:series_change", args=[self.series.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.requester)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Change the Timetable")

    def test_the_change_screen_previews_then_changes(self):
        self.client.force_login(self.requester)
        url = reverse("bookings:series_change", args=[self.series.pk])
        response = self.client.post(url, {
            "starts_on": self.change_on.isoformat(),
            "repeat_until": self.series.repeat_until.isoformat(),
            "venue": self.other_room.pk,
            "purpose": "Contract Law",
            "reason": "Faculty moved the class",
            "day_3": "on", "from_3": "14:00", "to_3": "16:00",
        })
        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.get(action="SERIES_CHANGED")
        self.assertIn("Seminar Room 2", log.description)
        self.assertNotIn("Faculty moved", log.description)


class ScheduleTooltipTests(Fixtures):
    def test_the_purpose_is_on_the_schedule_block(self):
        Booking.objects.create(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"),
            purpose="Moot rehearsal", status=BookingStatus.APPROVED,
        )
        self.client.force_login(self.requester)
        response = self.client.get(
            reverse("bookings:availability", args=[self.room.pk]), {"date": self.day.isoformat()}
        )
        self.assertContains(response, "data-tip=")
        self.assertContains(response, "Purpose: Moot rehearsal")
