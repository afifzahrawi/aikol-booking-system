"""Editable site identity and announcements."""

from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User

from ..models import Announcement, SiteContent


def make_user(email: str, role=Role.USER) -> User:
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name="Test User",
        affiliation=Affiliation.STAFF,
        role=role,
        email_verified=True,
    )


class SiteContentTests(TestCase):
    def setUp(self) -> None:
        self.admin = make_user("admin@demo.aikol.test", Role.ADMINISTRATOR)
        self.user = make_user("user@demo.aikol.test")

    def test_login_uses_the_editable_introduction(self):
        content = SiteContent.load()
        content.login_intro_heading = "Reserve AIKOL spaces"
        content.login_intro = "A factual introduction from the office."
        content.login_points = "First point\nSecond point"
        content.save()

        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, "Reserve AIKOL spaces")
        self.assertContains(response, "A factual introduction from the office.")
        self.assertContains(response, "First point")
        self.assertContains(response, "iium_logo_uploaded.jpg")

    def test_only_administrators_can_manage_announcements(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("administration:announcement_new")).status_code,
            403,
        )

    def test_administrator_can_create_an_announcement(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("administration:announcement_new"),
            {
                "title": "Office closure",
                "message": "Key collection closes at 4.30 pm.",
                "tone": Announcement.Tone.IMPORTANT,
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("administration:site_content"))
        self.assertTrue(Announcement.objects.filter(title="Office closure").exists())

    def test_current_announcement_appears_below_the_home_search(self):
        Announcement.objects.create(title="Current notice", message="Please read this.")
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(response, "Current notice")
        html = response.content.decode()
        self.assertLess(html.index("search-hero"), html.index("announcement-stack"))

    def test_inactive_expired_and_future_announcements_are_hidden(self):
        now = timezone.now()
        Announcement.objects.create(title="Inactive", message="Hidden", is_active=False)
        Announcement.objects.create(
            title="Expired",
            message="Hidden",
            ends_at=now - dt.timedelta(minutes=1),
        )
        Announcement.objects.create(
            title="Future",
            message="Hidden",
            starts_at=now + dt.timedelta(minutes=1),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:dashboard"))

        self.assertNotContains(response, "Inactive")
        self.assertNotContains(response, "Expired")
        self.assertNotContains(response, "Future")
