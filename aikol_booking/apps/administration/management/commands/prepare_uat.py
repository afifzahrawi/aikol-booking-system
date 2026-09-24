"""Reset production to a clean slate for user acceptance testing.

Removes every booking and everything hanging off one (series, key handovers,
archive copies), the audit log and delivered or failed email, deletes the test
venue(s) entered during setup, and adds three UAT venues illustrated with the
prototype's placeholder drawings. Users, settings, site content, announcements,
academic terms, facilities and vehicles are left exactly as they are.

This deliberately does what the application never does in normal operation:
deletes bookings and audit rows. It exists for the one moment before UAT when
the history is known to be test noise. It prints what it would do and changes
nothing unless --confirm is given, and it refuses to run a second time in a
database that already holds a UAT booking, so it cannot wipe the office's
acceptance testing once that has started. Take a backup first
(`backup_database`), as for any bulk deletion (decision 21).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.audit.models import AuditLog
from apps.bookings.models import Booking, BookingArchive, BookingSeries, KeyHandover
from apps.notifications.models import EmailOutbox, EmailStatus
from apps.resources.models import Facility, ResourceFacility, Venue

UAT_NOTE = (
    "UAT test venue for acceptance testing. Not a real Kulliyyah room: edit or "
    "deactivate it once testing is finished."
)

UAT_VENUES = [
    {
        "code": "UAT-VEN-01",
        "name": "UAT Moot Court",
        "venue_type": Venue.VenueType.MOOT_COURT,
        "location": "AIKOL Main Building (UAT)",
        "floor": "Level 1",
        "capacity": 80,
        "image_slug": "moot-court",
        "facilities": ["projector", "microphone", "sound", "aircond", "internet"],
    },
    {
        "code": "UAT-VEN-02",
        "name": "UAT Seminar Room",
        "venue_type": Venue.VenueType.SEMINAR,
        "location": "AIKOL Main Building (UAT)",
        "floor": "Level 2",
        "capacity": 40,
        "image_slug": "seminar-a",
        "facilities": ["projector", "whiteboard", "aircond", "internet"],
    },
    {
        "code": "UAT-VEN-03",
        "name": "UAT Meeting Room",
        "venue_type": Venue.VenueType.MEETING,
        "location": "AIKOL Main Building (UAT)",
        "floor": "Level 3",
        "capacity": 10,
        "image_slug": "meeting-a",
        "facilities": ["smart_tv", "whiteboard", "aircond", "video_conf"],
    },
]


class Command(BaseCommand):
    help = "Clear bookings and the audit log, replace test venues with three UAT venues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually make the changes. Without it the command only reports.",
        )
        parser.add_argument(
            "--test-venue-match",
            default="test",
            help="Venues whose name or code contains this text are deleted. Default: test.",
        )

    def handle(self, *args, **options):
        match = options["test_venue_match"].strip()
        if not match:
            raise CommandError("--test-venue-match must not be empty.")

        uat_codes = [row["code"] for row in UAT_VENUES]
        if Booking.objects.filter(resource__code__in=uat_codes).exists():
            raise CommandError(
                "A booking already refers to a UAT venue, so acceptance testing has started. "
                "Refusing to clear it."
            )

        test_venues = Venue.objects.filter(Q(name__icontains=match) | Q(code__icontains=match))
        finished_email = EmailOutbox.objects.exclude(status=EmailStatus.PENDING)
        counts = {
            "key handovers": KeyHandover.objects.count(),
            "bookings": Booking.objects.count(),
            "booking series": BookingSeries.objects.count(),
            "archived bookings": BookingArchive.objects.count(),
            "audit log entries": AuditLog.objects.count(),
            "sent or failed emails": finished_email.count(),
        }
        for label, count in counts.items():
            self.stdout.write(f"{count} {label} to remove.")
        for venue in test_venues:
            self.stdout.write(f"Test venue to delete: {venue.code}, {venue.name}.")
        if not test_venues:
            self.stdout.write(f'No venue name or code contains "{match}".')

        if not options["confirm"]:
            self.stdout.write("Nothing changed. Run again with --confirm to apply.")
            return

        with transaction.atomic():
            # Children before parents: every link to a booking or resource is PROTECT.
            KeyHandover.objects.all().delete()
            Booking.objects.all().delete()
            BookingSeries.objects.all().delete()
            BookingArchive.objects.all().delete()
            finished_email.delete()
            for venue in test_venues:
                venue.delete()
            created = self._create_uat_venues()
            # Last, so nothing written above leaves a row behind.
            AuditLog.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(f"Cleared. {created} UAT venue(s) created; users and settings kept.")
        )

    def _create_uat_venues(self) -> int:
        facilities = {f.code: f for f in Facility.objects.all()}
        created = 0
        for row in UAT_VENUES:
            wanted = dict(row)
            codes = wanted.pop("facilities")
            venue, made = Venue.objects.get_or_create(
                code=wanted["code"], defaults={**wanted, "description": UAT_NOTE}
            )
            if made:
                created += 1
                for code in codes:
                    if code in facilities:
                        ResourceFacility.objects.get_or_create(
                            resource=venue, facility=facilities[code]
                        )
            self.stdout.write(f"{venue.code}: {venue.name} ({'created' if made else 'kept'}).")
        return created
