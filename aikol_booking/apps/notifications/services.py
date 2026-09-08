"""The single way anything in this system sends email.

Never call send_mail() from a view. Queue a row; cron delivers it.
"""

from __future__ import annotations

from .models import EmailOutbox


def queue_email(*, to: str, subject: str, body: str, kind: str) -> EmailOutbox:
    """Write one message to the outbox.

    Call this inside the same transaction as the action it reports, so that a
    booking and its confirmation either both happen or neither does.
    """
    return EmailOutbox.objects.create(
        to_address=to, subject=subject, body=body, kind=kind
    )
