"""The single helper every other app uses to write to the audit log."""

from __future__ import annotations

from .models import AuditLog


def log_action(
    *,
    actor=None,
    action: str,
    entity_type: str = "",
    entity_id: str | int = "",
    description: str = "",
    request=None,
) -> AuditLog:
    ip = None
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
    return AuditLog.objects.create(
        actor=actor,
        actor_email=getattr(actor, "email", "") or "",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        description=description,
        ip_address=ip,
    )
