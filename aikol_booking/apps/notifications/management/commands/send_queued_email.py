"""Drain the email outbox. Run from cron every five minutes.

Idempotent: a row already SENT is never sent twice, and a run that dies halfway
leaves the remaining rows PENDING for the next one.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core.mail import get_connection, EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notifications.models import EmailOutbox, EmailStatus

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

        sent = failed = 0
        connection = get_connection()
        for row in pending:
            try:
                EmailMessage(
                    subject=row.subject,
                    body=row.body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
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
