"""The cloud bootstrap must never disclose the password in its output."""

from io import StringIO

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import Affiliation, Role


class BootstrapAdminTests(TestCase):
    def test_creates_verified_staff_admin_with_encrypted_handoff(self):
        key = Fernet.generate_key().decode()
        output = StringIO()
        with override_settings(CREDENTIAL_ENCRYPTION_KEY=key):
            call_command(
                "bootstrap_admin",
                email="bazlibaderul@iium.edu.my",
                full_name="Muhammad Bazli Bin Baderul Hisham",
                stdout=output,
            )
        token = output.getvalue().strip().split("=", 1)[1]
        password = Fernet(key.encode()).decrypt(token.encode()).decode()
        user = get_user_model().objects.get(email="bazlibaderul@iium.edu.my")
        self.assertEqual(user.full_name, "Muhammad Bazli Bin Baderul Hisham")
        self.assertEqual(user.affiliation, Affiliation.STAFF)
        self.assertEqual(user.role, Role.ADMINISTRATOR)
        self.assertTrue(user.is_staff and user.is_superuser and user.email_verified)
        self.assertIsNotNone(user.email_verified_at)
        self.assertTrue(user.check_password(password))
        self.assertNotIn(password, output.getvalue())
        with override_settings(CREDENTIAL_ENCRYPTION_KEY=key):
            with self.assertRaisesMessage(CommandError, "already exists"):
                call_command(
                    "bootstrap_admin",
                    email="bazlibaderul@iium.edu.my",
                    full_name="Muhammad Bazli Bin Baderul Hisham",
                )
        self.assertEqual(get_user_model().objects.count(), 1)
