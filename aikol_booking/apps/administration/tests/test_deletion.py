from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.bookings.models import AcademicTerm, Booking, BookingStatus
from apps.resources.models import Venue


def make_user(email, role=Role.USER, active=True):
    return User.objects.create_user(
        email=email, password="prototype-password-1", full_name=email.split("@")[0].title(),
        phone="03-6196 4000", affiliation=Affiliation.STAFF, role=role, email_verified=True,
        is_active=active,
    )


class AccountDeletionTests(TestCase):
    def setUp(self):
        self.admin = make_user("office@demo.aikol.test", Role.ADMINISTRATOR)
        self.client.force_login(self.admin)

    def test_an_active_account_is_not_offered_for_deletion(self):
        person = make_user("someone@demo.aikol.test")
        response = self.client.post(reverse("administration:user_delete", args=[person.pk]))
        self.assertContains(response, "still active")
        self.assertTrue(User.objects.filter(pk=person.pk).exists())

    def test_a_retired_account_with_history_stays(self):
        person = make_user("booked@demo.aikol.test", active=False)
        room = Venue.objects.create(code="R1", name="Room", venue_type=Venue.VenueType.MEETING,
                                    location="L1", capacity=5)
        start = timezone.now() + dt.timedelta(days=3)
        Booking.objects.create(resource=room, user=person, created_by=person, start_at=start,
                               end_at=start + dt.timedelta(hours=1), purpose="x",
                               status=BookingStatus.CANCELLED)
        response = self.client.post(reverse("administration:user_delete", args=[person.pk]))
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(User.objects.filter(pk=person.pk).exists())

    def test_a_retired_unused_account_is_deleted(self):
        person = make_user("mistake@demo.aikol.test", active=False)
        response = self.client.post(reverse("administration:user_delete", args=[person.pk]))
        self.assertRedirects(response, reverse("administration:users"))
        self.assertFalse(User.objects.filter(pk=person.pk).exists())

    def test_nobody_deletes_themselves(self):
        self.admin.is_active = True
        response = self.client.post(reverse("administration:user_delete", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())


class CalendarDeletionTests(TestCase):
    def test_an_administrator_deletes_a_calendar_and_bookings_are_untouched(self):
        admin = make_user("office@demo.aikol.test", Role.ADMINISTRATOR)
        self.client.force_login(admin)
        today = timezone.localdate()
        term = AcademicTerm.objects.create(name="Old semester", start_date=today,
                                           end_date=today + dt.timedelta(days=30))
        page = self.client.get(reverse("bookings:academic_term_delete", args=[term.pk]))
        self.assertContains(page, "Delete calendar")
        response = self.client.post(reverse("bookings:academic_term_delete", args=[term.pk]))
        self.assertRedirects(response, reverse("bookings:academic_terms"))
        self.assertFalse(AcademicTerm.objects.filter(pk=term.pk).exists())

    def test_an_ordinary_user_cannot(self):
        person = make_user("person@demo.aikol.test")
        self.client.force_login(person)
        today = timezone.localdate()
        term = AcademicTerm.objects.create(name="S", start_date=today, end_date=today + dt.timedelta(days=3))
        self.assertEqual(
            self.client.post(reverse("bookings:academic_term_delete", args=[term.pk])).status_code, 403
        )
