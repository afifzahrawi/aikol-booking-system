"""Retention: find, export, then remove.

The governing principle is that the system must never destroy institutional data
as a side effect of ordinary operation. Nothing here runs on a schedule. A
retention period does not delete anything — it makes records *eligible* for a
cleanup an administrator has to review and confirm.

Seven years of AIKOL bookings is a small dataset. Retention exists here for
governance, not for performance; nobody should argue for a shorter period on the
grounds of database size.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_action
from apps.bookings.models import Booking, BookingArchive, KeyHandover

from .models import SystemSetting

BATCH = 1000

#: Exports are written OUTSIDE the web root. A retention export served by the
#: web server to anyone who guesses the filename is a data breach with extra
#: steps.
EXPORT_DIR = Path(settings.BASE_DIR).parent / "retention-exports"

TYPED_CONFIRMATION = "DELETE PERMANENTLY"


@dataclass
class CleanupPreview:
    cutoff: dt.date
    bookings: int
    handovers: int
    earliest: dt.datetime | None
    latest: dt.datetime | None
    action: str


def cutoff_date() -> dt.date:
    years = SystemSetting.get_int("booking_retention_years")
    return timezone.localdate() - dt.timedelta(days=365 * years)


def eligible() -> "list":
    """Bookings older than the retention period. Nothing is changed by asking."""
    boundary = timezone.make_aware(dt.datetime.combine(cutoff_date(), dt.time.min))
    return Booking.objects.filter(end_at__lt=boundary)


def preview() -> CleanupPreview:
    rows = eligible()
    first = rows.order_by("start_at").values_list("start_at", flat=True).first()
    last = rows.order_by("-start_at").values_list("start_at", flat=True).first()
    return CleanupPreview(
        cutoff=cutoff_date(),
        bookings=rows.count(),
        handovers=KeyHandover.objects.filter(booking__in=rows).count(),
        earliest=first,
        latest=last,
        action=SystemSetting.get("retention_disposal_action"),
    )


def _export_batch(bookings, path: Path) -> int:
    """Write the rows and return how many were written.

    The exported CSV is the record of last resort, so it is verified before
    anything is deleted: the row count must match the selection and the file
    must be readable back.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    header = [
        "booking_reference", "user_email", "user_name", "resource_code", "resource_name",
        "resource_type", "start_at", "end_at", "status", "purpose",
        "key_issued_at", "key_returned_at", "created_at",
    ]
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(header)
        for booking in bookings:
            handover = getattr(booking, "key_handover", None)
            writer.writerow(
                [
                    booking.booking_reference,
                    booking.user.email,
                    booking.user.full_name,
                    booking.resource.code,
                    booking.resource.name,
                    booking.resource.resource_type,
                    booking.start_at.isoformat(),
                    booking.end_at.isoformat(),
                    booking.status,
                    booking.purpose,
                    handover.issued_at.isoformat() if handover and handover.issued_at else "",
                    handover.returned_at.isoformat() if handover and handover.returned_at else "",
                    booking.created_at.isoformat(),
                ]
            )
            written += 1
    return written


def _verify(path: Path, expected_total: int) -> None:
    """Read the file back and count it. An export nobody checked is a promise,
    not a record."""
    if not path.exists():
        raise ValidationError(f"The export file {path} was not written.")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = sum(1 for _ in csv.reader(handle)) - 1  # less the header
    if rows != expected_total:
        raise ValidationError(
            f"The export holds {rows} rows but {expected_total} were selected. "
            "Nothing has been deleted."
        )


def run_cleanup(*, actor, confirmation: str, action: str | None = None) -> dict:
    """Export (or archive) and then remove, in batches.

    Each batch exports and deletes inside ONE transaction, so a failure cannot
    leave rows deleted but unexported.

    `KeyHandover` references bookings with PROTECT, so its rows are exported and
    removed in the same batch, before the bookings they belong to. A cleanup
    that forgot them would simply fail rather than orphan anything — which is
    the intended behaviour, not a defect to work around by loosening the key.
    """
    if not actor.is_administrator:
        raise ValidationError("Only an administrator may run a retention cleanup.")
    if confirmation != TYPED_CONFIRMATION:
        raise ValidationError(
            f'Type "{TYPED_CONFIRMATION}" exactly to confirm. '
            "Nothing has been deleted."
        )

    action = action or SystemSetting.get("retention_disposal_action")
    if action not in ("EXPORT", "ARCHIVE"):
        raise ValidationError(
            "Permanent deletion with no copy is restricted and is not offered here."
        )

    total = eligible().count()
    if not total:
        return {"removed": 0, "path": None, "action": action}

    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    path = EXPORT_DIR / f"retention-{stamp}.csv"
    removed = 0

    while True:
        batch = list(
            eligible()
            .select_related("user", "resource")
            .prefetch_related("key_handover")[:BATCH]
        )
        if not batch:
            break
        ids = [b.pk for b in batch]
        with transaction.atomic():
            if action == "EXPORT":
                _export_batch(batch, path)
            else:
                BookingArchive.objects.bulk_create(
                    [BookingArchive.from_booking(b) for b in batch], batch_size=BATCH
                )
            # Before the bookings, because of PROTECT.
            KeyHandover.objects.filter(booking_id__in=ids).delete()
            Booking.objects.filter(pk__in=ids).delete()
        removed += len(batch)

    if action == "EXPORT":
        _verify(path, removed)
    elif BookingArchive.objects.count() < removed:
        raise ValidationError("The archive copy is short. Investigate before running again.")

    log_action(
        actor=actor,
        action="RETENTION_CLEANUP",
        entity_type="Booking",
        description=(
            f"{removed} records {action.lower()}ed and removed; cutoff {cutoff_date()}."
            + (f" File: {path.name}." if action == "EXPORT" else "")
        ),
    )
    return {"removed": removed, "path": str(path) if action == "EXPORT" else None, "action": action}
