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
