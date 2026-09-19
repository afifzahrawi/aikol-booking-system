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

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils import timezone

from cryptography.fernet import Fernet, InvalidToken


class EmailStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


def _credential_cipher() -> Fernet:
    """Return the application cipher used for administrator-managed secrets."""
    key = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", "")
    if not key:
        raise ImproperlyConfigured(
            "DJANGO_CREDENTIAL_ENCRYPTION_KEY is required for stored email credentials."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "DJANGO_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


class EmailConfiguration(models.Model):
    """The single SMTP profile used by the Python outbox worker.

    The password is encrypted before it reaches the database and is never
    rendered back into an administrator form or audit record.
    """

    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255, blank=True)
    encrypted_password = models.TextField(blank=True, editable=False)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    default_from_email = models.CharField(
        max_length=255,
        default="AIKOL Booking <booking-aikol@iium.edu.my>",
    )
    timeout_seconds = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "email delivery configuration"
        verbose_name_plural = "email delivery configuration"

    def __str__(self) -> str:
        return self.host or "Email delivery not configured"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "EmailConfiguration":
        configuration, _ = cls.objects.get_or_create(pk=1)
        return configuration

    @property
    def has_password(self) -> bool:
        return bool(self.encrypted_password)

    @property
    def is_ready(self) -> bool:
        return bool(self.is_active and self.host and self.default_from_email)

    def set_password(self, password: str) -> None:
        self.encrypted_password = (
            _credential_cipher().encrypt(password.encode("utf-8")).decode("ascii")
            if password
            else ""
        )

    def get_password(self) -> str:
        if not self.encrypted_password:
            return ""
        try:
            return _credential_cipher().decrypt(
                self.encrypted_password.encode("ascii")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ImproperlyConfigured(
                "The stored SMTP password cannot be decrypted with the configured key."
            ) from exc


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
