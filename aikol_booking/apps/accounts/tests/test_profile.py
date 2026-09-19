"""Self-service profile editing and account-action navigation."""

from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.notifications.models import EmailOutbox

from ..models import Affiliation, Role, User


class ProfileEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="person@demo.aikol.test",
            password="prototype-password-1",
            full_name="Original Name",
            phone="03-6196 4000",
            identification_number="S1234",
            affiliation=Affiliation.STUDENT,
            role=Role.USER,
            email_verified=True,
        )

    def test_profile_requires_sign_in(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(
            response,
            reverse("accounts:login") + "?next=" + reverse("accounts:profile"),
        )

    def test_profile_edits_email_but_not_governed_details(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, self.user.email)
        self.assertContains(response, self.user.identification_number)
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="role"')

    def test_person_can_update_name_and_phone(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "full_name": "Updated Name",
                "email": self.user.email,
                "phone": "+60 12-345 6789",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Updated Name")
        self.assertEqual(self.user.phone, "+60 12-345 6789")
        self.assertEqual(self.user.email, "person@demo.aikol.test")
        self.assertTrue(
            AuditLog.objects.filter(actor=self.user, action="PROFILE_UPDATED").exists()
        )

    def test_email_change_requires_fresh_verification_and_queues_email(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "full_name": self.user.full_name,
                "email": "New.Address@iium.edu.my",
                "phone": self.user.phone,
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new.address@iium.edu.my")
        self.assertFalse(self.user.email_verified)
        self.assertIsNone(self.user.email_verified_at)
        verification = EmailOutbox.objects.get(kind="ACCOUNT_VERIFY")
        self.assertEqual(verification.to_address, "new.address@iium.edu.my")

    def test_email_change_rejects_an_address_already_in_use(self):
        User.objects.create_user(
            email="taken@iium.edu.my",
            password="prototype-password-2",
            full_name="Another Person",
            identification_number="S5678",
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "full_name": self.user.full_name,
                "email": "taken@iium.edu.my",
                "phone": self.user.phone,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User with this Email address already exists")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "person@demo.aikol.test")

    def test_navigation_uses_edit_profile_and_distinct_sign_out_actions(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("accounts:dashboard")).content.decode()
        self.assertIn('class="nav-profile"', html)
        self.assertIn('class="nav-profile-icon"', html)
        self.assertIn(reverse("accounts:profile"), html)
        self.assertIn("Edit Profile", html)
        self.assertIn("Sign Out", html)
        self.assertNotIn(self.user.initials, html)
        self.assertLess(html.index('class="nav-profile-icon"'), html.index('class="nav-profile-name"'))
        self.assertLess(html.index('class="brand-iium"'), html.index('class="brand-aikol"'))
        self.assertNotIn("logo-divider", html)
