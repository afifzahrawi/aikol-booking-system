"""The nine facilities that exist at installation.

These are seeded rather than hard-coded: an administrator can rename, deactivate
or add to them afterwards without a software release. `is_seeded` records which
ones came from here, so the Facilities screen can say so.
"""

from django.core.management.base import BaseCommand

from apps.resources.models import Facility

SEEDED = [
    ("projector", "Projector", Facility.AppliesTo.VENUE),
    ("microphone", "Microphone", Facility.AppliesTo.VENUE),
    ("smart_tv", "Smart Television", Facility.AppliesTo.VENUE),
    ("whiteboard", "Whiteboard", Facility.AppliesTo.VENUE),
    ("computer", "Computer", Facility.AppliesTo.VENUE),
    ("internet", "Internet Access", Facility.AppliesTo.BOTH),
    ("aircond", "Air Conditioning", Facility.AppliesTo.BOTH),
    ("sound", "Sound System", Facility.AppliesTo.VENUE),
    ("video_conf", "Video Conferencing", Facility.AppliesTo.VENUE),
]


class Command(BaseCommand):
    help = "Create the installation facility list if it is missing."

    def handle(self, *args, **options):
        created = 0
        for order, (code, name, applies) in enumerate(SEEDED, start=1):
            _, made = Facility.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "applies_to": applies,
                    "display_order": order,
                    "is_seeded": True,
                },
            )
            created += int(made)
        self.stdout.write(f"facilities_created={created}")
