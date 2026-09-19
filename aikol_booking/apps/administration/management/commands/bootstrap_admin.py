"""One-time production administrator bootstrap with an encrypted password handoff."""

from __future__ import annotations

import secrets

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Affiliation


class Command(BaseCommand):
    help = "Create one administrator and print only an encrypted password handoff token."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--full-name", required=True)

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        full_name = options["full_name"].strip()
        if not email.endswith("@iium.edu.my") or not full_name:
            raise CommandError("A full name and an @iium.edu.my address are required.")

        try:
            cipher = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        except (AttributeError, TypeError, ValueError) as exc:
            raise CommandError("The credential encryption key is invalid.") from exc

        user_model = get_user_model()
        password = secrets.token_urlsafe(32)
        token = cipher.encrypt(password.encode()).decode()
        with transaction.atomic():
            if user_model.objects.filter(email__iexact=email).exists():
                raise CommandError("This account already exists; no password was changed.")
            user_model.objects.create_superuser(
                email=email,
                password=password,
                full_name=full_name,
                affiliation=Affiliation.STAFF,
                email_verified_at=timezone.now(),
            )

        self.stdout.write(f"AIKOL_ADMIN_HANDOFF_TOKEN={token}")
