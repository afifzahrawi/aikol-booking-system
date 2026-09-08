"""Move APPROVED bookings whose end_at has passed to COMPLETED. Daily, from cron.

Idempotent, and deliberately narrow: it only touches APPROVED rows that are
already over. It never cancels, never deletes, and never touches a PENDING
booking — an unanswered request that has expired is a decision somebody still
owes, not something to tidy away automatically.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus


class Command(BaseCommand):
    help = "Transition finished approved bookings to COMPLETED."

    def handle(self, *args, **options):
        count = Booking.objects.filter(
            status=BookingStatus.APPROVED, end_at__lt=timezone.now()
        ).update(status=BookingStatus.COMPLETED)
        self.stdout.write(f"completed={count}")
