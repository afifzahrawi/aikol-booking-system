from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Affiliation, Role, User
from apps.audit.models import AuditLog
from apps.notifications.models import EmailOutbox, EmailWording
from apps.notifications.wording import EMAILS, fill, render, send


def make_user(email, role=Role.USER):
    return User.objects.create_user(
        email=email, password="prototype-password-1", full_name=email.split("@")[0].title(),
        phone="03-6196 4000", affiliation=Affiliation.STAFF, role=role, email_verified=True,
    )


class WordingTests(TestCase):
    def test_every_default_uses_only_its_own_fields(self):
        from apps.notifications.wording import problems

        for key, spec in EMAILS.items():
            self.assertEqual(problems(key, spec.subject, spec.body), [], key)

    def test_the_default_is_used_until_the_office_changes_it(self):
        subject, body = render("BOOKING_CANCELLED", {**EMAILS["BOOKING_CANCELLED"].sample})
        self.assertIn("BK-202610-0004", subject)
        EmailWording.objects.create(
            key="BOOKING_CANCELLED", subject="Cancelled {reference}", body="Dear {name}, gone."
        )
        subject, body = render("BOOKING_CANCELLED", EMAILS["BOOKING_CANCELLED"].sample)
        self.assertEqual(subject, "Cancelled BK-202610-0004")
        self.assertEqual(body, "Dear Nurul Aisyah, gone.\n")

    def test_a_value_is_inserted_exactly_as_it_is(self):
        """A purpose typed as "{reason}" must not be expanded a second time,
        and nothing can reach an attribute the way str.format would allow."""
        self.assertEqual(
            fill("{purpose} / {reason}", {"purpose": "{reason}", "reason": "R"}), "{reason} / R"
        )
        self.assertEqual(fill("{user.password}", {"user": object()}), "{user.password}")

    def test_sending_uses_the_edited_wording(self):
        EmailWording.objects.create(key="ACCOUNT_IMPORTED", subject="Welcome", body="Hi {name}.")
        send("ACCOUNT_IMPORTED", to="x@iium.edu.my", values={"name": "Aiman"})
        row = EmailOutbox.objects.get(kind="ACCOUNT_IMPORTED")
        self.assertEqual((row.subject, row.body), ("Welcome", "Hi Aiman.\n"))


class EmailScreenTests(TestCase):
    def setUp(self):
        self.admin = make_user("office@demo.aikol.test", Role.ADMINISTRATOR)
        self.client.force_login(self.admin)
        self.url = reverse("administration:email_edit", args=["ACCOUNT_VERIFY"])

    def test_the_list_shows_every_email(self):
        page = self.client.get(reverse("administration:email_list"))
        for spec in EMAILS.values():
            self.assertContains(page, spec.label)

    def test_saving_changes_the_wording_and_is_logged(self):
        response = self.client.post(self.url, {
            "action": "save", "subject": "Confirm now",
            "body": "Salam {name}, click {link} within {days} days.",
        })
        self.assertRedirects(response, reverse("administration:email_list"))
        row = EmailWording.objects.get(key="ACCOUNT_VERIFY")
        self.assertEqual(row.updated_by, self.admin)
        self.assertTrue(AuditLog.objects.filter(action="EMAIL_WORDING_CHANGED").exists())

    def test_a_field_the_email_cannot_fill_is_refused(self):
        response = self.client.post(self.url, {
            "action": "save", "subject": "Hi", "body": "{link} for {reference}",
        })
        self.assertContains(response, "cannot fill in {reference}")
        self.assertFalse(EmailWording.objects.exists())

    def test_the_link_cannot_be_removed(self):
        """Without the link nobody could confirm their address."""
        response = self.client.post(self.url, {
            "action": "save", "subject": "Hi", "body": "Welcome, {name}.",
        })
        self.assertContains(response, "Keep {link} in the email")
        self.assertFalse(EmailWording.objects.exists())

    def test_preview_fills_sample_details_and_saves_nothing(self):
        response = self.client.post(self.url, {
            "action": "preview", "subject": "Hi {name}", "body": "Go to {link}",
        })
        self.assertContains(response, "Hi Nurul Aisyah")
        self.assertContains(response, "https://aikol-booking.example/verify/")
        self.assertFalse(EmailWording.objects.exists())

    def test_reset_puts_the_default_back(self):
        EmailWording.objects.create(key="ACCOUNT_VERIFY", subject="X", body="{link}")
        self.client.post(self.url, {"action": "reset"})
        self.assertFalse(EmailWording.objects.exists())

    def test_an_unknown_email_is_not_found(self):
        self.assertEqual(
            self.client.get(reverse("administration:email_edit", args=["NOPE"])).status_code, 404
        )

    def test_an_approver_cannot_edit_emails(self):
        self.client.force_login(make_user("approver@demo.aikol.test", Role.APPROVER))
        self.assertEqual(self.client.get(reverse("administration:email_list")).status_code, 403)
