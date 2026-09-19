"""The second factor: the algorithm against the RFC, then the door it guards.

Enforcement is off for the rest of the suite (see config/testrunner.py) and
switched on here, so these are the tests that prove an approver or an
administrator cannot get anywhere without it.
"""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts import mfa
from apps.accounts.models import Affiliation, RecoveryCode, Role, TotpDevice, User
from apps.audit.models import AuditLog

#: RFC 6238, Appendix B. The secret is the ASCII string "12345678901234567890".
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
RFC_VECTORS = (
    (59, "94287082"),
    (1111111109, "07081804"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
)


class AlgorithmTests(TestCase):
    def test_the_rfc_test_vectors(self):
        for at, expected in RFC_VECTORS:
            with self.subTest(at=at):
                self.assertEqual(mfa.totp(RFC_SECRET, at=at, digits=8), expected)

    def test_six_digits_are_the_last_six(self):
        self.assertEqual(mfa.totp(RFC_SECRET, at=59), "287082")

    def test_the_window_is_one_step_either_side(self):
        now = 1234567890
        code = mfa.totp(RFC_SECRET, at=now)
        self.assertIsNotNone(mfa.verify(RFC_SECRET, code, at=now - 30))
        self.assertIsNotNone(mfa.verify(RFC_SECRET, code, at=now + 30))
        self.assertIsNone(mfa.verify(RFC_SECRET, code, at=now + 60))

    def test_a_code_is_good_once(self):
        now = 1234567890
        code = mfa.totp(RFC_SECRET, at=now)
        step = mfa.verify(RFC_SECRET, code, at=now)
        self.assertIsNone(mfa.verify(RFC_SECRET, code, at=now, after_step=step))

    def test_spaces_in_a_code_are_forgiven_and_letters_are_not(self):
        self.assertIsNotNone(mfa.verify(RFC_SECRET, "287 082", at=59))
        self.assertIsNone(mfa.verify(RFC_SECRET, "28708a", at=59))
        self.assertIsNone(mfa.verify(RFC_SECRET, "", at=59))

    def test_a_fresh_secret_is_base32_and_160_bits(self):
        secret = mfa.generate_secret()
        self.assertEqual(len(secret), 32)
        self.assertTrue(set(secret) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"))

    def test_the_provisioning_uri_names_the_issuer_and_account(self):
        uri = mfa.provisioning_uri("ABC", "a@iium.edu.my", "AIKOL Booking")
        self.assertTrue(uri.startswith("otpauth://totp/AIKOL%20Booking%3Aa%40iium.edu.my?"))
        self.assertIn("secret=ABC", uri)
        self.assertIn("issuer=AIKOL%20Booking", uri)

    def test_the_qr_is_inline_svg(self):
        svg = mfa.qr_svg("otpauth://totp/x?secret=ABC")
        self.assertTrue(svg.lstrip().startswith("<svg"))


class Fixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        def person(email, role):
            return User.objects.create_user(
                email=email, password="prototype-password-1", full_name=email.split("@")[0],
                phone="03-6196 4000", email_verified=True, role=role,
                affiliation=Affiliation.STAFF,
            )
        cls.admin = person("admin@demo.aikol.test", Role.ADMINISTRATOR)
        cls.other_admin = person("admin2@demo.aikol.test", Role.ADMINISTRATOR)
        cls.approver = person("approver@demo.aikol.test", Role.APPROVER)
        cls.user = person("user@demo.aikol.test", Role.USER)

    def enrol(self, person) -> TotpDevice:
        device = TotpDevice(user=person)
        device.set_secret(mfa.generate_secret())
        device.confirmed_at = person.date_joined
        device.save()
        return device

    def code_for(self, device, offset_steps: int = 0) -> str:
        """A code the device would show now. Tests that need a second, distinct
        code ask for the next step, so nothing here waits thirty seconds."""
        import time
        return mfa.totp(device.secret, at=time.time() + offset_steps * mfa.STEP_SECONDS)

    def verify_session(self, person, device):
        self.client.force_login(person)
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": self.code_for(device)})
        self.assertEqual(response.status_code, 302)


@override_settings(MFA_ENFORCED=True)
class EnforcementTests(Fixtures):
    def test_an_administrator_without_an_authenticator_is_sent_to_enrol(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("administration:users"))
        self.assertRedirects(
            response,
            reverse("accounts:mfa_enrol") + "?next=" + reverse("administration:users"),
            fetch_redirect_response=False,
        )

    def test_an_approver_is_gated_too(self):
        self.client.force_login(self.approver)
        response = self.client.get(reverse("bookings:approvals"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:mfa_enrol"), response["Location"])

    def test_an_ordinary_user_is_not(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("bookings:mine")).status_code, 200)

    def test_djangos_own_admin_is_gated(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:mfa_enrol"), response["Location"])

    def test_the_door_out_stays_open(self):
        """Somebody without their phone must still be able to sign out."""
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("authenticator", response["Location"])

    def test_the_gated_pages_show_no_navigation(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("accounts:mfa_enrol")).content.decode()
        self.assertNotIn('class="app-nav"', html)
        self.assertIn("Sign out instead", html)


@override_settings(MFA_ENFORCED=True)
class EnrolmentTests(Fixtures):
    def test_enrolment_shows_a_qr_and_the_key_and_creates_an_unconfirmed_device(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:mfa_enrol"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("<svg", html)
        device = TotpDevice.objects.get(user=self.admin)
        self.assertFalse(device.confirmed)
        self.assertIn(mfa.grouped(device.secret), html)
        self.assertNotIn(device.secret, device.encrypted_secret, "stored encrypted")

    def test_a_wrong_code_does_not_confirm(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("accounts:mfa_enrol"))
        response = self.client.post(reverse("accounts:mfa_enrol"), {"code": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("did not match", response.content.decode())
        self.assertFalse(TotpDevice.objects.get(user=self.admin).confirmed)
        self.assertEqual(RecoveryCode.objects.filter(user=self.admin).count(), 0)

    def test_the_right_code_confirms_issues_codes_and_opens_the_door(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("accounts:mfa_enrol"))
        device = TotpDevice.objects.get(user=self.admin)
        target = reverse("administration:users")
        response = self.client.post(
            reverse("accounts:mfa_enrol"), {"code": self.code_for(device), "next": target}
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("recovery codes", html.lower())
        self.assertIn(f'href="{target}"', html)
        self.assertTrue(TotpDevice.objects.get(user=self.admin).confirmed)
        self.assertEqual(RecoveryCode.objects.filter(user=self.admin).count(), 10)
        self.assertTrue(AuditLog.objects.filter(action="MFA_ENROLLED", actor=self.admin).exists())
        # And the session is verified: the page they wanted now renders.
        self.assertEqual(self.client.get(target).status_code, 200)

    def test_recovery_codes_are_stored_hashed(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("accounts:mfa_enrol"))
        device = TotpDevice.objects.get(user=self.admin)
        html = self.client.post(
            reverse("accounts:mfa_enrol"), {"code": self.code_for(device)}
        ).content.decode()
        for row in RecoveryCode.objects.filter(user=self.admin):
            self.assertNotIn(row.code_hash, html)
            self.assertTrue(row.code_hash.startswith(("pbkdf2", "argon2", "scrypt", "bcrypt")))

    def test_an_enrolled_person_is_sent_to_verify_not_enrol(self):
        self.enrol(self.admin)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:mfa_enrol"))
        self.assertRedirects(response, reverse("accounts:mfa_verify"), fetch_redirect_response=False)

    def test_an_open_redirect_is_not_honoured(self):
        self.client.force_login(self.admin)
        self.client.get(reverse("accounts:mfa_enrol"))
        device = TotpDevice.objects.get(user=self.admin)
        html = self.client.post(
            reverse("accounts:mfa_enrol"),
            {"code": self.code_for(device), "next": "https://evil.example/"},
        ).content.decode()
        self.assertNotIn("evil.example", html)
        self.assertIn(f'href="{reverse("accounts:dashboard")}"', html)


@override_settings(MFA_ENFORCED=True)
class VerificationTests(Fixtures):
    def setUp(self):
        self.device = self.enrol(self.admin)

    def test_an_enrolled_administrator_is_asked_for_a_code_each_session(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("administration:users"))
        self.assertIn(reverse("accounts:mfa_verify"), response["Location"])

    def test_the_right_code_opens_the_session(self):
        self.client.force_login(self.admin)
        target = reverse("administration:settings")
        response = self.client.post(
            reverse("accounts:mfa_verify"), {"code": self.code_for(self.device), "next": target}
        )
        self.assertRedirects(response, target, fetch_redirect_response=False)
        self.assertEqual(self.client.get(target).status_code, 200)

    def test_a_wrong_code_does_not(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": "123456"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(reverse("accounts:mfa_verify"),
                      self.client.get(reverse("administration:users"))["Location"])

    def test_a_code_cannot_be_replayed_in_a_second_session(self):
        code = self.code_for(self.device)
        self.verify_session(self.admin, self.device)
        self.client.logout()
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": code})
        self.assertEqual(response.status_code, 200)
        self.assertIn("did not match", response.content.decode())

    def test_a_recovery_code_works_once_and_is_logged(self):
        codes = RecoveryCode.issue(self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": codes[0]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RecoveryCode.objects.filter(user=self.admin, used_at__isnull=True).count(), 9)
        self.assertTrue(AuditLog.objects.filter(action="MFA_RECOVERY_CODE_USED", actor=self.admin).exists())
        self.assertEqual(self.client.get(reverse("administration:users")).status_code, 200)

        self.client.logout()
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": codes[0]})
        self.assertEqual(response.status_code, 200, "the same code again is refused")

    def test_a_recovery_code_is_not_another_persons(self):
        codes = RecoveryCode.issue(self.other_admin)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": codes[0]})
        self.assertEqual(response.status_code, 200)

    def test_verification_is_rate_limited(self):
        self.client.force_login(self.admin)
        for _ in range(10):
            self.client.post(reverse("accounts:mfa_verify"), {"code": "000000"})
        response = self.client.post(reverse("accounts:mfa_verify"), {"code": self.code_for(self.device)})
        self.assertEqual(response.status_code, 429, "even the right code, once the bucket is full")

    def test_a_verified_session_survives_ordinary_navigation(self):
        self.verify_session(self.admin, self.device)
        for name in ("administration:dashboard", "bookings:approvals", "accounts:profile"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


@override_settings(MFA_ENFORCED=True)
class ResetTests(Fixtures):
    def test_an_administrator_resets_a_colleague_and_ends_their_sessions(self):
        device = self.enrol(self.approver)
        RecoveryCode.issue(self.approver)
        approver_client = self.client_class()
        approver_client.force_login(self.approver)
        approver_client.post(reverse("accounts:mfa_verify"), {"code": self.code_for(device)})
        self.assertEqual(approver_client.get(reverse("bookings:approvals")).status_code, 200)

        admin_device = self.enrol(self.admin)
        self.verify_session(self.admin, admin_device)
        response = self.client.post(reverse("administration:user_mfa_reset", args=[self.approver.pk]))
        self.assertRedirects(response, reverse("administration:user_edit", args=[self.approver.pk]),
                             fetch_redirect_response=False)
        self.assertFalse(TotpDevice.objects.filter(user=self.approver).exists())
        self.assertEqual(RecoveryCode.objects.filter(user=self.approver).count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="USER_MFA_RESET", entity_id=str(self.approver.pk)).exists())

        response = approver_client.get(reverse("bookings:approvals"))
        self.assertIn(reverse("accounts:mfa_enrol"), response["Location"], "their session is no longer verified")

    def test_nobody_resets_their_own(self):
        device = self.enrol(self.admin)
        self.verify_session(self.admin, device)
        response = self.client.post(reverse("administration:user_mfa_reset", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(TotpDevice.objects.filter(user=self.admin).exists())

    def test_the_edit_screen_shows_enrolment_state(self):
        device = self.enrol(self.admin)
        self.verify_session(self.admin, device)
        html = self.client.get(reverse("administration:user_edit", args=[self.approver.pk])).content.decode()
        self.assertIn("Not yet enrolled", html)
        self.enrol(self.approver)
        html = self.client.get(reverse("administration:user_edit", args=[self.approver.pk])).content.decode()
        self.assertIn("Reset authenticator", html)
        html = self.client.get(reverse("administration:user_edit", args=[self.user.pk])).content.decode()
        self.assertIn("Only approvers and administrators", html)

    def test_the_command_resets_the_last_administrator(self):
        self.enrol(self.admin)
        RecoveryCode.issue(self.admin)
        call_command("reset_mfa", email=self.admin.email)
        self.assertFalse(TotpDevice.objects.filter(user=self.admin).exists())
        self.assertEqual(RecoveryCode.objects.filter(user=self.admin).count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="USER_MFA_RESET", entity_id=str(self.admin.pk)).exists())
