"""The email-verification token.

A signed, time-limited value derived from the account's own state rather than a
column: including `email_verified` means the token stops working the moment it
is used, with nothing to store or clean up.
"""

from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp: int) -> str:
        return f"{user.pk}{user.email}{timestamp}{user.email_verified}"


email_verification_token = EmailVerificationTokenGenerator()
