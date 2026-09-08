"""The audit log. Append-only: application code never edits or deletes a row."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    # The actor may be deactivated later but never deleted while log rows point
    # at them; SET_NULL covers the case where a row predates a purge.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    actor_email = models.EmailField(
        blank=True, help_text="Denormalised, so the entry stays readable regardless."
    )
    action = models.CharField(max_length=60)
    entity_type = models.CharField(max_length=40, blank=True)
    entity_id = models.CharField(max_length=40, blank=True)
    # Free text. Driving licence and telephone numbers are personal data and
    # must never appear here.
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"
