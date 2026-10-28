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
        # The bullet points are no longer shown on the simplified sign-in page.
        self.assertNotContains(response, "First point")
        self.assertContains(response, "iium_logo.png")

    def test_footer_lists_fax_every_email_and_the_copyright_last(self):
        content = SiteContent.load()
        content.fax = "03-6196 4001"
        content.email = "booking@iium.edu.my\nkeys@iium.edu.my"
        content.save()
        self.client.force_login(self.user)

        page = self.client.get(reverse("resources:venues")).content.decode()
        footer = page[page.index('<footer class="app-footer">'):page.index("</footer>")]

        self.assertIn("Fax: 03-6196 4001", footer)
        self.assertIn('href="mailto:booking@iium.edu.my"', footer)
        self.assertIn('href="mailto:keys@iium.edu.my"', footer)
        self.assertNotIn("Institution", footer)
        self.assertIn(f"&copy; {timezone.localdate().year} International Islamic", footer)
        self.assertGreater(footer.index("footer-copyright"), footer.index("mailto:keys"))

    def test_site_content_form_refuses_an_address_that_is_not_one(self):
        from ..forms import SiteContentForm

        data = {name: getattr(SiteContent.load(), name) for name in SiteContentForm.Meta.fields
                if not name.endswith(("logo", "image"))}
        data["email"] = "booking@iium.edu.my\n\n  not an address  "
        form = SiteContentForm(data, instance=SiteContent.load())
        self.assertFalse(form.is_valid())
        self.assertIn("not an address", str(form.errors["email"]))
        data["email"] = " booking@iium.edu.my \n\nkeys@iium.edu.my"
        form = SiteContentForm(data, instance=SiteContent.load())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "booking@iium.edu.my\nkeys@iium.edu.my")

    def test_page_notices_come_from_site_content_and_hide_when_blank(self):
        user = User.objects.create_user(
            email="notice@demo.aikol.test", password="prototype-password-1",
            full_name="Notice Reader", phone="03-6196 4000", email_verified=True,
        )
        self.client.force_login(user)
        vehicles = self.client.get(reverse("resources:vehicles"))
        self.assertContains(vehicles, "Driver arrangement is included.")
        self.assertNotContains(self.client.get(reverse("resources:venues")), "Venue booking information")

        content = SiteContent.load()
        content.vehicle_list_notice_heading = "Book two days ahead."
        content.vehicle_list_notice = "Drivers are arranged on weekdays."
        content.venue_list_notice_heading = "Keys from the office."
        content.save()
        vehicles = self.client.get(reverse("resources:vehicles"))
        self.assertContains(vehicles, "Book two days ahead.")
        self.assertNotContains(vehicles, "Driver arrangement is included.")
        self.assertContains(self.client.get(reverse("resources:venues")), "Keys from the office.")

    def test_the_admin_edits_a_notice_on_its_page_and_returns_there(self):
        admin = User.objects.create_user(
            email="notice-admin@demo.aikol.test", password="prototype-password-1",
            full_name="Notice Admin", phone="03-6196 4000", email_verified=True,
            role=Role.ADMINISTRATOR,
        )
        self.client.force_login(admin)
        page = self.client.get(reverse("resources:vehicles"))
        edit_url = reverse("administration:page_notice_edit", args=["vehicle_list"])
        self.assertContains(page, edit_url)
        # The venue notice starts empty: the Admin sees a slot to add one.
        self.assertContains(self.client.get(reverse("resources:venues")), "Add a notice for this page")

        response = self.client.post(
            edit_url,
            {"heading": "Book two days ahead.", "text": "Drivers work weekdays.", "next": "/cars/"},
        )
        self.assertRedirects(response, "/cars/", fetch_redirect_response=False)
        content = SiteContent.load()
        self.assertEqual(content.vehicle_list_notice_heading, "Book two days ahead.")
        self.assertEqual(content.vehicle_list_notice, "Drivers work weekdays.")

        # A next address on another site is ignored.
        response = self.client.post(
            edit_url, {"heading": "", "text": "", "next": "https://example.com/"}
        )
        self.assertRedirects(
            response, reverse("administration:site_content"), fetch_redirect_response=False
        )

    def test_only_the_admin_sees_or_uses_the_notice_editor(self):
        user = User.objects.create_user(
            email="notice-user@demo.aikol.test", password="prototype-password-1",
            full_name="Notice User", phone="03-6196 4000", email_verified=True,
        )
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse("resources:vehicles")), "notice-edit")
        self.assertNotContains(self.client.get(reverse("resources:venues")), "Add a notice")
        edit_url = reverse("administration:page_notice_edit", args=["vehicle_list"])
        self.assertEqual(self.client.post(edit_url, {"heading": "x"}).status_code, 403)

    def test_an_uploaded_logo_loses_its_white_and_is_sized_for_the_header(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image, ImageDraw

        from ..forms import SiteContentForm

        # A dark ring on a white sheet: the sheet and the white inside the ring
        # (like the hole in an O) must both become transparent.
        sheet = Image.new("RGB", (800, 400), "white")
        ImageDraw.Draw(sheet).ellipse((200, 50, 600, 350), outline="black", width=60)
        buffer = BytesIO()
        sheet.save(buffer, format="JPEG")
        upload = SimpleUploadedFile("crest.jpg", buffer.getvalue(), content_type="image/jpeg")

        data = {name: getattr(SiteContent.load(), name) for name in SiteContentForm.Meta.fields
                if not name.endswith(("logo", "image"))}
        form = SiteContentForm(data, {"logo": upload}, instance=SiteContent.load())
        self.assertTrue(form.is_valid(), form.errors)
        logo = form.cleaned_data["logo"]
        self.assertTrue(logo.name.endswith(".png"))
        with Image.open(BytesIO(logo.read())) as stored:
            stored = stored.convert("RGBA")
            self.assertEqual(stored.height, 160)
            centre = (stored.width // 2, stored.height // 2)
            self.assertEqual(stored.getpixel((0, 0))[3], 0)
            self.assertEqual(stored.getpixel(centre)[3], 0)
            self.assertEqual(stored.getpixel((stored.width // 2, 25))[3], 255)

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
                "is_active": "True",
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
        self.assertLess(html.index("capsule-search"), html.index("announcement-stack"))

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
