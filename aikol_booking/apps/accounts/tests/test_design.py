"""The design defects the audit found, pinned so they cannot come back."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

CSS = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")


class StylesheetTests(TestCase):
    def test_focus_is_shown_to_keyboard_users_not_mouse_users(self):
        """`:focus` fires on click too. Buttons and links had no focus rule at
        all, so a keyboard user could not see where they were."""
        self.assertIn(".btn:focus-visible", CSS)
        self.assertIn(".app-nav a:focus-visible", CSS)

    def test_buttons_respond_to_being_pressed(self):
        self.assertRegex(CSS, r"\.btn:active[^{]*\{[^}]*transform:\s*scale")

    def test_motion_is_reducible(self):
        self.assertIn("prefers-reduced-motion", CSS)

    def test_no_transition_names_all(self):
        """`transition: all` animates properties nobody chose, including
        layout ones that cost a repaint."""
        self.assertNotIn("transition: all", CSS)

    def test_numbers_in_tables_are_tabular(self):
        self.assertIn("tabular-nums", CSS)


class FormStylingTests(TestCase):
    """The stylesheet styles controls by class. Django renders none, so every
    form in the application was unstyled until the mixin was added."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="person@demo.aikol.test", password="prototype-password-1",
            full_name="Person", phone="03-6196 4000", email_verified=True,
        )

    def styled(self, html: str) -> tuple[int, int]:
        controls = len(re.findall(r"<(?:input|select|textarea)\b", html))
        classed = len(re.findall(r'class="[^"]*\b(?:input|select|textarea)\b', html))
        return controls, classed

    def test_the_registration_form_controls_are_styled(self):
        html = self.client.get(reverse("accounts:register")).content.decode()
        controls, classed = self.styled(html)
        self.assertGreater(controls, 3)
        # Every control except the CSRF hidden field and the tick box.
        self.assertGreaterEqual(classed, controls - 2)

    def test_the_sign_in_form_controls_are_styled(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn('class="input"', html)

    def test_a_required_field_says_so_to_assistive_technology(self):
        html = self.client.get(reverse("accounts:register")).content.decode()
        self.assertIn('aria-required="true"', html)

    def test_a_checkbox_is_not_given_a_text_field_class(self):
        """`.input` on a checkbox would give it a 300px-wide bordered box."""
        html = self.client.get(reverse("accounts:register")).content.decode()
        checkbox = re.search(r'<input[^>]*type="checkbox"[^>]*>', html)
        self.assertIsNotNone(checkbox)
        self.assertNotIn("input", checkbox.group(0).split('class="')[-1].split('"')[0]
                         if 'class="' in checkbox.group(0) else "")


class FormPresentationTests(TestCase):
    """The remaining gaps from the audit: error styling, field pairing, and
    help text a screen reader can actually reach."""

    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin@demo.aikol.test", password="prototype-password-1",
            full_name="Admin", phone="03-6196 4000", email_verified=True,
            role="ADMINISTRATOR",
        )

    def test_djangos_error_markup_is_styled(self):
        self.assertIn(".errorlist", CSS)

    def test_an_invalid_submission_renders_styled_errors(self):
        html = self.client.post(reverse("accounts:register"), {"email": "nope"}).content.decode()
        self.assertIn("errorlist", html)

    def test_help_text_is_associated_with_its_control(self):
        """Otherwise a screen-reader user hears the label and nothing else."""
        from django.urls import reverse as url

        self.client.force_login(self.admin)
        html = self.client.get(url("resources:vehicle_new")).content.decode()
        self.assertIn('aria-describedby="help_road_tax_expiry"', html)
        self.assertIn('id="help_road_tax_expiry"', html)

    def test_paired_fields_render_side_by_side(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("resources:venue_new")).content.decode()
        self.assertIn('class="field-row"', html)

    def test_a_form_with_no_layout_still_renders_every_field(self):
        """`rows()` must not drop anything when `layout` is empty."""
        from apps.bookings.forms import CancellationForm

        form = CancellationForm()
        rendered = {f.name for _, fields in form.rows() for f in fields}
        self.assertEqual(rendered, set(form.fields))

    def test_a_layout_naming_a_removed_field_does_not_break(self):
        """The booking form drops fields depending on the resource kind."""
        from apps.bookings.forms import BookingForm
        from apps.resources.models import Venue

        venue = Venue.objects.create(
            code="VEN-L", name="Room", venue_type=Venue.VenueType.SEMINAR,
            location="L1", capacity=10,
        )
        form = BookingForm(resource=venue, user=self.admin)
        rendered = {f.name for _, fields in form.rows() for f in fields}
        self.assertEqual(rendered, set(form.fields))
        self.assertNotIn("passengers", rendered, "a venue has no passenger field")


class ProgressiveEnhancementTests(TestCase):
    """The live availability check warns early. It decides nothing."""

    def setUp(self) -> None:
        from apps.administration.models import SystemSetting
        from apps.resources.models import Venue

        SystemSetting.seed()
        self.user = User.objects.create_user(
            email="user@demo.aikol.test", password="prototype-password-1",
            full_name="User", phone="03-6196 4000", email_verified=True,
        )
        self.venue = Venue.objects.create(
            code="VEN-1", name="Room", venue_type=Venue.VenueType.SEMINAR,
            location="L1", capacity=10,
        )
        self.client.force_login(self.user)

    def day(self):
        import datetime as dt

        from django.utils import timezone

        return (timezone.localdate() + dt.timedelta(days=10)).isoformat()

    def test_a_free_slot_reports_free(self):
        from django.urls import reverse as url

        response = self.client.get(
            url("bookings:slot_check", args=[self.venue.pk]),
            {"start_date": self.day(), "start_time": "10:00", "end_time": "12:00"},
        )
        self.assertTrue(response.json()["free"])

    def test_a_taken_slot_reports_the_clash(self):
        import datetime as dt

        from django.urls import reverse as url
        from django.utils import timezone

        from apps.bookings.models import Booking, BookingStatus

        start = timezone.make_aware(
            dt.datetime.combine(dt.date.fromisoformat(self.day()), dt.time(10, 0))
        )
        Booking.objects.create(
            resource=self.venue, user=self.user, created_by=self.user,
            start_at=start, end_at=start + dt.timedelta(hours=2),
            purpose="Taken", status=BookingStatus.APPROVED,
        )
        response = self.client.get(
            url("bookings:slot_check", args=[self.venue.pk]),
            {"start_date": self.day(), "start_time": "11:00", "end_time": "13:00"},
        )
        body = response.json()
        self.assertFalse(body["free"])
        self.assertIn("Already reserved", body["message"])

    def test_the_endpoint_changes_nothing(self):
        from django.urls import reverse as url

        from apps.bookings.models import Booking

        self.client.get(
            url("bookings:slot_check", args=[self.venue.pk]),
            {"start_date": self.day(), "start_time": "10:00", "end_time": "12:00"},
        )
        self.assertEqual(Booking.objects.count(), 0)

    def test_it_needs_a_signed_in_user(self):
        from django.urls import reverse as url

        self.client.logout()
        response = self.client.get(url("bookings:slot_check", args=[self.venue.pk]))
        self.assertEqual(response.status_code, 302)

    def test_the_server_still_refuses_a_clash_when_the_check_is_bypassed(self):
        """The endpoint is a courtesy. Posting straight past it must still fail."""
        import datetime as dt

        from django.urls import reverse as url
        from django.utils import timezone

        from apps.bookings.models import Booking, BookingStatus

        start = timezone.make_aware(
            dt.datetime.combine(dt.date.fromisoformat(self.day()), dt.time(10, 0))
        )
        Booking.objects.create(
            resource=self.venue, user=self.user, created_by=self.user,
            start_at=start, end_at=start + dt.timedelta(hours=2),
            purpose="Taken", status=BookingStatus.APPROVED,
        )
        response = self.client.post(
            url("bookings:create", args=[self.venue.pk]),
            {"start_date": self.day(), "start_time": "11:00", "end_time": "13:00",
             "purpose": "Ignoring the warning", "attendees": "5"},
        )
        self.assertContains(response, "Already reserved")
        self.assertEqual(Booking.objects.count(), 1)
