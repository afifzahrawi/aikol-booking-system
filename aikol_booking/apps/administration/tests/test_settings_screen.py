from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Affiliation, Role, User
from apps.administration.models import SystemSetting


class SettingsScreenTests(TestCase):
    def setUp(self):
        SystemSetting.seed()
        self.admin = User.objects.create_user(
            email="office@demo.aikol.test",
            password="prototype-password-1",
            full_name="Kulliyyah Office",
            phone="03-6196 4000",
            affiliation=Affiliation.STAFF,
            role=Role.ADMINISTRATOR,
            email_verified=True,
        )
        self.client.force_login(self.admin)

    def test_a_yes_no_setting_is_offered_as_a_choice_and_saved_as_a_flag(self):
        page = self.client.get(reverse("administration:settings"))
        self.assertContains(page, 'id="setting-cancellation_reason_required"')
        self.assertContains(page, "<option value=\"0\">No</option>", html=False)
        self.client.post(
            reverse("administration:settings"),
            {"key": "cancellation_reason_required", "value": "0"},
        )
        self.assertEqual(SystemSetting.get("cancellation_reason_required"), "0")
        self.assertFalse(SystemSetting.get_bool("cancellation_reason_required"))

    def test_a_value_outside_the_offered_choices_is_refused(self):
        self.client.post(
            reverse("administration:settings"),
            {"key": "cancellation_reason_required", "value": "maybe"},
        )
        self.assertEqual(SystemSetting.get("cancellation_reason_required"), "1")
        self.client.post(
            reverse("administration:settings"),
            {"key": "advance_booking_limit_days", "value": "ninety"},
        )
        self.assertEqual(SystemSetting.get("advance_booking_limit_days"), "90")

    def test_descriptions_carry_no_decision_numbers(self):
        page = self.client.get(reverse("administration:settings"))
        self.assertNotContains(page, "decision ")
