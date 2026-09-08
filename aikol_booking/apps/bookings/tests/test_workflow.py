"""Recurring series, approval, cancellation and the confirmation emails.

The email tests assert on `email_outbox` rows rather than on `mail.outbox`,
because the outbox table is where this system's own guarantee lives: the row is
written in the same transaction as the booking, and cron delivers it later.
"""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.administration.models import SystemSetting
from apps.bookings.models import (
    AcademicTerm,
    Booking,
    BookingSeries,
    BookingStatus,
    TermBreak,
)
from apps.bookings.services import (
    approve_booking,
    approve_series,
    cancel_booking,
    cancel_series,
    create_booking,
    create_series,
    reject_booking,
)
from apps.notifications.models import EmailOutbox
from apps.resources.models import Venue

from .test_conflicts import at


def make_user(email: str, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name=extra.pop("full_name", email.split("@")[0].title()),
        phone="012-345 6789",
        email_verified=True,
        **extra,
    )


class Fixtures(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        self.requester = make_user(
            "requester@demo.aikol.test",
            affiliation=Affiliation.LECTURER,
            identification_number="STAFF-9001",
        )
        self.approver = make_user("approver@demo.aikol.test", role=Role.APPROVER)
        self.admin = make_user("admin@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.room = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        self.day = timezone.localdate() + dt.timedelta(days=14)

        today = timezone.localdate()
        self.term = AcademicTerm.objects.create(
            name="Semester 1",
            start_date=today - dt.timedelta(days=14),
            end_date=today + dt.timedelta(days=80),
        )
        # The first Monday at least a week away, so nothing lands in the past.
        self.monday = today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)

    def outbox(self, kind: str):
        return EmailOutbox.objects.filter(kind=kind)


class SubmissionEmailTests(Fixtures):
    def test_a_submission_queues_one_row_addressed_to_the_requester(self):
        booking = create_booking(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Tutorial",
        )
        row = self.outbox("BOOKING_SUBMITTED").get()
        self.assertEqual(row.to_address, self.requester.email)
        self.assertIn(booking.booking_reference, row.body)

    def test_a_booking_made_on_someones_behalf_emails_the_user_not_the_creator(self):
        create_booking(
            resource=self.room, user=self.requester, created_by=self.admin,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Meeting",
        )
        row = self.outbox("BOOKING_SUBMITTED").get()
        self.assertEqual(row.to_address, self.requester.email)
        self.assertNotEqual(row.to_address, self.admin.email)
        self.assertIn("on your behalf", row.body)

    def test_a_rolled_back_booking_leaves_no_outbox_row(self):
        """The row is written in the same transaction as the booking. If the
        booking does not survive, neither does the message."""
        try:
            with transaction.atomic():
                create_booking(
                    resource=self.room, user=self.requester, created_by=self.requester,
                    start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"),
                    purpose="Doomed",
                )
                raise RuntimeError("something failed after the booking")
        except RuntimeError:
            pass
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(EmailOutbox.objects.count(), 0)

    def test_no_email_carries_a_matriculation_or_telephone_number(self):
        booking = create_booking(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Tutorial",
        )
        approve_booking(booking, decided_by=self.approver)
        cancel_booking(booking, cancelled_by=self.approver, reason="Room needed for an exam")
        for row in EmailOutbox.objects.all():
            with self.subTest(kind=row.kind):
                self.assertNotIn("STAFF-9001", row.body)
                self.assertNotIn("012-345 6789", row.body)


class ApprovalTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.booking = create_booking(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Tutorial",
        )

    def test_approving_records_who_and_when_and_emails_the_requester(self):
        approve_booking(self.booking, decided_by=self.approver)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.APPROVED)
        self.assertEqual(self.booking.decided_by, self.approver)
        self.assertIsNotNone(self.booking.decided_at)
        self.assertEqual(self.outbox("BOOKING_APPROVED").count(), 1)

    def test_rejecting_requires_a_reason_and_sends_it(self):
        with self.assertRaises(ValidationError):
            reject_booking(self.booking, decided_by=self.approver, reason="   ")
        reject_booking(self.booking, decided_by=self.approver, reason="Clashes with an exam")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.REJECTED)
        self.assertIn("Clashes with an exam", self.outbox("BOOKING_REJECTED").get().body)

    def test_a_pending_request_already_holds_its_slot(self):
        """So a second overlapping request cannot be made at all, and the
        approval-time re-check is not defending against this case."""
        with self.assertRaises(ValidationError):
            create_booking(
                resource=self.room, user=self.admin, created_by=self.admin,
                start_at=at(self.day, "11:00"), end_at=at(self.day, "13:00"), purpose="Other",
            )

    def test_a_slot_taken_after_submission_cannot_be_approved_over(self):
        """The overlapping row is created directly, because that is the only way
        one can arise: a bulk import, an administrator amending times, or a
        shell session — any path that does not go through `create_booking`.
        Approval is the last moment before the resource is promised to somebody,
        so it looks again."""
        Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "11:00"), end_at=at(self.day, "13:00"),
            purpose="Arrived by another path", status=BookingStatus.APPROVED,
        )

        with self.assertRaises(ValidationError) as ctx:
            approve_booking(self.booking, decided_by=self.approver)
        self.assertIn("approved for another booking since", str(ctx.exception))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PENDING, "and it is not overwritten")

    def test_a_booking_cannot_be_approved_twice(self):
        approve_booking(self.booking, decided_by=self.approver)
        with self.assertRaises(ValidationError):
            approve_booking(self.booking, decided_by=self.approver)
        self.assertEqual(self.outbox("BOOKING_APPROVED").count(), 1)


class CancellationTests(Fixtures):
    def test_a_reason_is_mandatory(self):
        booking = create_booking(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Tutorial",
        )
        with self.assertRaises(ValidationError):
            cancel_booking(booking, cancelled_by=self.requester, reason="")

    def test_cancelling_sets_a_status_and_never_deletes(self):
        booking = create_booking(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Tutorial",
        )
        cancel_booking(booking, cancelled_by=self.requester, reason="No longer needed")
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertIsNotNone(booking.cancelled_at)
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    def test_a_cancelled_slot_becomes_free_again(self):
        booking = create_booking(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="First",
        )
        cancel_booking(booking, cancelled_by=self.requester, reason="Plans changed")
        replacement = create_booking(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Second",
        )
        self.assertEqual(replacement.status, BookingStatus.PENDING)

    def test_a_user_cannot_cancel_inside_the_three_day_cutoff(self):
        soon = Booking.objects.create(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=timezone.now() + dt.timedelta(hours=24),
            end_at=timezone.now() + dt.timedelta(hours=26),
            purpose="Tomorrow",
        )
        with self.assertRaises(ValidationError) as ctx:
            cancel_booking(soon, cancelled_by=self.requester, reason="Changed my mind")
        self.assertIn("3 days' notice", str(ctx.exception))

    def test_an_approver_is_not_bound_by_the_cutoff(self):
        soon = Booking.objects.create(
            resource=self.room, user=self.requester, created_by=self.requester,
            start_at=timezone.now() + dt.timedelta(hours=24),
            end_at=timezone.now() + dt.timedelta(hours=26),
            purpose="Tomorrow",
        )
        cancel_booking(soon, cancelled_by=self.approver, reason="Room needed for an exam")
        soon.refresh_from_db()
        self.assertEqual(soon.status, BookingStatus.CANCELLED)


class SeriesTests(Fixtures):
    def weekly(self, **overrides):
        params = {
            "resource": self.room,
            "user": self.requester,
            "created_by": self.requester,
            "term": self.term,
            "weekday_times": {"0": ["09:00", "11:00"]},
            "starts_on": self.monday,
            "repeat_until": self.monday + dt.timedelta(days=28),
            "purpose": "Contract Law tutorial",
        }
        params.update(overrides)
        return create_series(**params)

    def test_a_clear_series_creates_every_occurrence_under_one_series_id(self):
        series, created, plan = self.weekly()
        self.assertEqual(len(created), 5)
        self.assertEqual({b.series_id for b in created}, {series.pk})
        self.assertEqual(Booking.objects.filter(series=series).count(), 5)
        self.assertTrue(all(b.status == BookingStatus.PENDING for b in created))

    def test_a_series_sends_one_summary_email_not_one_per_occurrence(self):
        self.weekly()
        self.assertEqual(self.outbox("SERIES_SUBMITTED").count(), 1)
        self.assertEqual(
            self.outbox("BOOKING_SUBMITTED").count(), 0,
            "an occurrence must not queue its own message",
        )

    def test_a_clash_is_reported_and_the_whole_request_is_refused(self):
        """Never silently skip. The requester decides what to do about week 2."""
        clash_day = self.monday + dt.timedelta(days=7)
        Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(clash_day, "09:00"), end_at=at(clash_day, "11:00"),
            purpose="Already there", status=BookingStatus.APPROVED,
        )
        with self.assertRaises(ValidationError) as ctx:
            self.weekly()
        self.assertIn("already reserved", str(ctx.exception))
        self.assertEqual(BookingSeries.objects.count(), 0, "and nothing is created")
        self.assertEqual(Booking.objects.filter(series__isnull=False).count(), 0)

    def test_accepting_a_partial_series_creates_the_rest(self):
        clash_day = self.monday + dt.timedelta(days=7)
        Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(clash_day, "09:00"), end_at=at(clash_day, "11:00"),
            purpose="Already there", status=BookingStatus.APPROVED,
        )
        series, created, plan = self.weekly(accept_partial=True)
        self.assertEqual(len(created), 4)
        self.assertEqual(len(plan["clashing"]), 1)
        self.assertNotIn(
            clash_day, [timezone.localtime(b.start_at).date() for b in created]
        )

    def test_the_summary_email_lists_what_was_left_out(self):
        clash_day = self.monday + dt.timedelta(days=7)
        Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(clash_day, "09:00"), end_at=at(clash_day, "11:00"),
            purpose="Already there", status=BookingStatus.APPROVED,
        )
        self.weekly(accept_partial=True)
        body = self.outbox("SERIES_SUBMITTED").get().body
        self.assertIn("Not included", body)
        self.assertIn("already reserved", body)

    def test_a_break_week_is_left_out_and_named(self):
        break_day = self.monday + dt.timedelta(days=7)
        TermBreak.objects.create(
            term=self.term, name="Mid-semester break",
            start_date=break_day, end_date=break_day + dt.timedelta(days=6),
        )
        series, created, plan = self.weekly()
        self.assertEqual(len(created), 4)
        self.assertEqual(len(plan["outside"]), 1)
        self.assertEqual(plan["outside"][0]["skip_reason"], "mid-semester break")

    def test_each_weekday_keeps_its_own_times(self):
        series, created, plan = self.weekly(
            weekday_times={"0": ["09:00", "11:00"], "3": ["14:00", "16:00"]},
            repeat_until=self.monday + dt.timedelta(days=7),
        )
        by_weekday = {
            timezone.localtime(b.start_at).weekday(): timezone.localtime(b.start_at).hour
            for b in created
        }
        self.assertEqual(by_weekday[0], 9)
        self.assertEqual(by_weekday[3], 14)

    def test_a_series_ending_before_it_starts_is_refused(self):
        with self.assertRaises(ValidationError):
            self.weekly(repeat_until=self.monday - dt.timedelta(days=1))

    def test_a_series_with_no_bookable_date_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.weekly(weekday_times={"5": ["09:00", "11:00"]}, repeat_until=self.monday)
        self.assertIn("No date in that range", str(ctx.exception))
        self.assertEqual(BookingSeries.objects.count(), 0)

    def test_expansion_is_atomic_so_a_failure_leaves_nothing(self):
        """Half a timetable is worse than none, because it looks complete."""
        from unittest import mock

        with mock.patch(
            "apps.bookings.services.create_booking", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.weekly()
        self.assertEqual(BookingSeries.objects.count(), 0)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(EmailOutbox.objects.count(), 0)

    def test_approving_a_series_rechecks_each_occurrence_and_sends_one_email(self):
        series, created, _ = self.weekly()
        approved, refused = approve_series(series, decided_by=self.approver)
        self.assertEqual(len(approved), 5)
        self.assertEqual(refused, [])
        self.assertEqual(self.outbox("SERIES_APPROVED").count(), 1)
        self.assertEqual(
            self.outbox("BOOKING_APPROVED").count(), 0,
            "not one message per occurrence",
        )

    def test_an_occurrence_overtaken_since_submission_is_reported_not_forced(self):
        series, created, _ = self.weekly()
        overtaken = created[2]
        # Somebody else's request for the same slot gets approved first.
        rival = Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=overtaken.start_at, end_at=overtaken.end_at,
            purpose="Rival", status=BookingStatus.APPROVED,
        )
        approved, refused = approve_series(series, decided_by=self.approver)
        self.assertEqual(len(approved), 4)
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0][0].pk, overtaken.pk)
        overtaken.refresh_from_db()
        self.assertEqual(overtaken.status, BookingStatus.PENDING)

    def test_cancelling_a_series_touches_only_future_occurrences(self):
        series, created, _ = self.weekly()
        # Drag the first two into the past, as if the semester had begun.
        past = created[:2]
        for offset, booking in enumerate(past, start=1):
            Booking.objects.filter(pk=booking.pk).update(
                start_at=timezone.now() - dt.timedelta(days=offset * 7),
                end_at=timezone.now() - dt.timedelta(days=offset * 7) + dt.timedelta(hours=2),
            )
        count = cancel_series(series, cancelled_by=self.requester, reason="Course withdrawn")
        self.assertEqual(count, 3)
        for booking in past:
            booking.refresh_from_db()
            self.assertEqual(booking.status, BookingStatus.PENDING, "history is untouched")
        self.assertEqual(self.outbox("SERIES_CANCELLED").count(), 1)

    def test_cancelling_one_occurrence_leaves_its_siblings_alone(self):
        series, created, _ = self.weekly()
        cancel_booking(created[1], cancelled_by=self.requester, reason="Public holiday")
        statuses = list(
            Booking.objects.filter(series=series).order_by("start_at").values_list("status", flat=True)
        )
        self.assertEqual(
            statuses,
            [
                BookingStatus.PENDING, BookingStatus.CANCELLED, BookingStatus.PENDING,
                BookingStatus.PENDING, BookingStatus.PENDING,
            ],
        )


class BookingViewTests(Fixtures):
    def test_an_unverified_account_cannot_reach_the_booking_form(self):
        unverified = make_user("new@demo.aikol.test")
        unverified.email_verified = False
        unverified.save(update_fields=["email_verified"])
        self.client.force_login(unverified)
        response = self.client.get(reverse("bookings:create", args=[self.room.pk]))
        self.assertEqual(response.status_code, 403)

    def test_a_verified_user_submits_a_booking_through_the_form(self):
        self.client.force_login(self.requester)
        response = self.client.post(
            reverse("bookings:create", args=[self.room.pk]),
            {
                "start_date": self.day.isoformat(),
                "start_time": "10:00",
                "end_time": "12:00",
                "purpose": "Contract Law tutorial",
                "attendees": "20",
            },
        )
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get()
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(booking.user, self.requester)
        self.assertEqual(booking.created_by, self.requester)

    def test_the_form_refuses_more_attendees_than_the_room_seats(self):
        self.client.force_login(self.requester)
        response = self.client.post(
            reverse("bookings:create", args=[self.room.pk]),
            {
                "start_date": self.day.isoformat(), "start_time": "10:00", "end_time": "12:00",
                "purpose": "Too many", "attendees": "500",
            },
        )
        self.assertContains(response, "seats 30")
        self.assertEqual(Booking.objects.count(), 0)

    def test_a_clash_is_reported_on_the_form_rather_than_created(self):
        Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"),
            purpose="Already there", status=BookingStatus.APPROVED,
        )
        self.client.force_login(self.requester)
        response = self.client.post(
            reverse("bookings:create", args=[self.room.pk]),
            {
                "start_date": self.day.isoformat(), "start_time": "11:00", "end_time": "13:00",
                "purpose": "Clashing", "attendees": "10",
            },
        )
        self.assertContains(response, "Already reserved")
        self.assertEqual(Booking.objects.count(), 1)

    def test_a_user_cannot_read_somebody_elses_booking(self):
        booking = create_booking(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"), purpose="Private",
        )
        self.client.force_login(self.requester)
        self.assertEqual(
            self.client.get(reverse("bookings:detail", args=[booking.pk])).status_code, 403
        )

    def test_an_ordinary_user_cannot_reach_the_approvals_queue(self):
        self.client.force_login(self.requester)
        self.assertEqual(self.client.get(reverse("bookings:approvals")).status_code, 403)

    def test_an_approver_can(self):
        self.client.force_login(self.approver)
        self.assertEqual(self.client.get(reverse("bookings:approvals")).status_code, 200)

    def test_the_availability_screen_shows_what_is_taken(self):
        Booking.objects.create(
            resource=self.room, user=self.admin, created_by=self.admin,
            start_at=at(self.day, "10:00"), end_at=at(self.day, "12:00"),
            purpose="Taken", status=BookingStatus.APPROVED,
        )
        self.client.force_login(self.requester)
        response = self.client.get(
            reverse("bookings:availability", args=[self.room.pk]), {"date": self.day.isoformat()}
        )
        self.assertContains(response, "Approved")
        self.assertContains(response, self.day.strftime("%A"))
