"""Outbound email, through a table rather than a queue.

A row is written in the SAME transaction as the action that caused it, and cron
drains it every five minutes. Two reasons, both concrete:

  - A booking must never fail because a mail server is slow.
  - A semester-long series must never hold a request open behind 26 SMTP
    round-trips.

This is one table and one cron entry that the design already had. It is not a
message queue and does not reopen that decision.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class EmailStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class EmailOutbox(models.Model):
    to_address = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    # What caused it — BOOKING_SUBMITTED, BOOKING_APPROVED, ACCOUNT_VERIFY and
    # so on. Kept so a failure can be traced to the action, not just the address.
    kind = models.CharField(max_length=40)
    status = models.CharField(
        max_length=10, choices=EmailStatus.choices, default=EmailStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=["status", "created_at"])]
        verbose_name_plural = "email outbox"

    def __str__(self) -> str:
        return f"{self.kind} to {self.to_address} ({self.status})"

    def mark_sent(self) -> None:
        self.status = EmailStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def mark_failed(self, error: str) -> None:
        self.status = EmailStatus.FAILED
        self.attempts += 1
        self.last_error = error[:2000]
        self.save(update_fields=["status", "attempts", "last_error"])
