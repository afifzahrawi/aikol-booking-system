from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Affiliation, Role, User
from apps.notifications.models import EmailConfiguration
from apps.notifications.models import EmailOutbox


class EmailSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@demo.aikol.test",
            password="prototype-password-1",
            full_name="Office Administrator",
            affiliation=Affiliation.STAFF,
            role=Role.ADMINISTRATOR,
            email_verified=True,
        )
        self.client.force_login(self.admin)

    def test_administrator_can_store_encrypted_smtp_credentials(self):
        response = self.client.post(
            reverse("administration:settings"),
            {
                "form_kind": "email",
                "email-host": "smtp.example.test",
                "email-port": "587",
                "email-username": "mailer",
                "email-password": "smtp-secret-value",
                "email-encryption": "tls",
                "email-default_from_email": "AIKOL Booking <booking@example.test>",
                "email-timeout_seconds": "20",
                "email-is_active": "True",
            },
        )

        self.assertRedirects(response, reverse("administration:settings"))
        configuration = EmailConfiguration.load()
        self.assertEqual(configuration.get_password(), "smtp-secret-value")
        self.assertNotIn("smtp-secret-value", configuration.encrypted_password)

        page = self.client.get(reverse("administration:settings"))
        self.assertNotContains(page, "smtp-secret-value")
        self.assertContains(page, "A password is saved")

    def test_blank_password_keeps_the_existing_secret(self):
        configuration = EmailConfiguration.load()
        configuration.set_password("keep-this-secret")
        configuration.save()

        self.client.post(
            reverse("administration:settings"),
            {
                "form_kind": "email",
                "email-host": "smtp.example.test",
                "email-port": "587",
                "email-username": "mailer",
                "email-password": "",
                "email-encryption": "tls",
                "email-default_from_email": "booking@example.test",
                "email-timeout_seconds": "20",
                "email-is_active": "True",
            },
        )

        configuration.refresh_from_db()
        self.assertEqual(configuration.get_password(), "keep-this-secret")

    def test_settings_explain_why_verification_mail_is_queued(self):
        EmailOutbox.objects.create(
            to_address="new@iium.edu.my", subject="Confirm", body="Test", kind="ACCOUNT_VERIFY"
        )
        page = self.client.get(reverse("administration:settings"))
        self.assertContains(page, "Email delivery is off")
        self.assertContains(page, "1 message await delivery")

    def test_modal_user_verification_returns_empty_success_response(self):
        person = User.objects.create_user(
            email="new@iium.edu.my",
            password="not-a-production-password",
            full_name="New Requester",
            phone="03-6196 4000",
            affiliation=Affiliation.STAFF,
            email_verified=False,
        )
        response = self.client.post(
            reverse("administration:user_edit", args=[person.pk]),
            {
                "full_name": person.full_name,
                "email": person.email,
                "identification_number": "",
                "phone": person.phone,
                "affiliation": person.affiliation,
                "role": person.role,
                "is_active": "True",
                "email_verified": "True",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        person.refresh_from_db()
        self.assertTrue(person.email_verified)
        self.assertIsNotNone(person.email_verified_at)
