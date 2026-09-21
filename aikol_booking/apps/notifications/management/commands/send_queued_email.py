"""Drain the email outbox. Run from the scheduler every minute.

Idempotent: a row already SENT is never sent twice, and a run that dies halfway
leaves the remaining rows PENDING for the next one.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core.mail import get_connection, EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notifications.models import EmailConfiguration, EmailOutbox, EmailStatus

MAX_ATTEMPTS = 5
PRUNE_AFTER_DAYS = 90


class Command(BaseCommand):
    help = "Send pending rows from the email outbox, retry failures, prune old sent rows."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        pending = EmailOutbox.objects.filter(
            status__in=(EmailStatus.PENDING, EmailStatus.FAILED),
            attempts__lt=MAX_ATTEMPTS,
        ).order_by("created_at")[: options["limit"]]

        configuration = EmailConfiguration.load()
        if configuration.is_ready:
            connection = get_connection(
                backend="django.core.mail.backends.smtp.EmailBackend",
                host=configuration.host,
                port=configuration.port,
                username=configuration.username,
                password=configuration.get_password(),
                use_tls=configuration.use_tls,
                use_ssl=configuration.use_ssl,
                timeout=configuration.timeout_seconds,
            )
            from_email = configuration.default_from_email
        elif settings.DEBUG:
            connection = get_connection()
            from_email = settings.DEFAULT_FROM_EMAIL
        else:
            self.stderr.write(
                "Email delivery is disabled or incomplete. Pending messages were left queued."
            )
            return

        sent = failed = 0
        for row in pending:
            try:
                EmailMessage(
                    subject=row.subject,
                    body=row.body,
                    from_email=from_email,
                    to=[row.to_address],
                    connection=connection,
                ).send(fail_silently=False)
            except Exception as exc:  # noqa: BLE001 - the error is recorded, not swallowed
                row.mark_failed(str(exc))
                failed += 1
            else:
                row.mark_sent()
                sent += 1

        cutoff = timezone.now() - dt.timedelta(days=PRUNE_AFTER_DAYS)
        pruned, _ = EmailOutbox.objects.filter(
            status=EmailStatus.SENT, sent_at__lt=cutoff
        ).delete()

        self.stdout.write(f"sent={sent} failed={failed} pruned={pruned}")
