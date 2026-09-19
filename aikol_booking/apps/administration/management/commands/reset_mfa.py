"""Reset one person's authenticator from the command line.

The screen in user management covers every case but one: the only remaining
administrator has lost their phone and their recovery codes, so nobody can sign
in to reset anybody. This runs where `bootstrap_admin` runs — as a Cloud Run
job by the account owner — and is written to the audit log like the screen.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.services import log_action


class Command(BaseCommand):
    help = "Remove a person's authenticator and recovery codes so they enrol again at next sign-in."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        try:
            person = get_user_model().objects.get(email__iexact=email)
        except get_user_model().DoesNotExist as exc:
            raise CommandError("No account with that address.") from exc
        device = getattr(person, "totp_device", None)
        if device is None:
            self.stdout.write("No authenticator enrolled; nothing to reset.")
            return
        with transaction.atomic():
            device.delete()
            person.recovery_codes.all().delete()
            log_action(
                actor=None,
                action="USER_MFA_RESET",
                entity_type="User",
                entity_id=person.pk,
                description=f"Authenticator reset for {person.full_name} by the reset_mfa command.",
            )
        self.stdout.write(f"Authenticator reset. {person.full_name} enrols again at next sign-in.")
