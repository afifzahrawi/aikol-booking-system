from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.notifications.models import EmailConfiguration, EmailOutbox, EmailStatus


class EmailDeliveryCommandTests(TestCase):
    @override_settings(DEBUG=False)
    def test_disabled_configuration_leaves_messages_queued(self):
        row = EmailOutbox.objects.create(
            to_address="person@example.test",
            subject="Queued",
            body="Message body",
            kind="TEST",
        )
        stderr = StringIO()

        call_command("send_queued_email", stderr=stderr)

        row.refresh_from_db()
        self.assertEqual(row.status, EmailStatus.PENDING)
        self.assertIn("disabled or incomplete", stderr.getvalue())

    @override_settings(DEBUG=False)
    @patch("apps.notifications.management.commands.send_queued_email.get_connection")
    def test_active_configuration_sends_with_decrypted_password(self, get_connection):
        connection = get_connection.return_value
        connection.send_messages.return_value = 1
        configuration = EmailConfiguration.load()
        configuration.host = "smtp.example.test"
        configuration.username = "mailer"
        configuration.default_from_email = "AIKOL Booking <booking@example.test>"
        configuration.is_active = True
        configuration.set_password("not-plain-text")
        configuration.save()
        row = EmailOutbox.objects.create(
            to_address="person@example.test",
            subject="Queued",
            body="Message body",
            kind="TEST",
        )

        call_command("send_queued_email", stdout=StringIO())

        row.refresh_from_db()
        self.assertEqual(row.status, EmailStatus.SENT)
        self.assertNotIn("not-plain-text", configuration.encrypted_password)
        self.assertEqual(get_connection.call_args.kwargs["password"], "not-plain-text")
        self.assertEqual(get_connection.call_args.kwargs["host"], "smtp.example.test")
