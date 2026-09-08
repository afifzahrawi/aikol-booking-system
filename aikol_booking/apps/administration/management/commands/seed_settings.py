"""Create any missing system setting at its confirmed default.

Idempotent, so it is safe to run on every deployment. The values come from
AIKOL's answers; see SystemSetting.DEFAULTS, where each names its decision.
"""

from django.core.management.base import BaseCommand

from apps.administration.models import SiteContent, SystemSetting


class Command(BaseCommand):
    help = "Seed system settings and site content with their confirmed defaults."

    def handle(self, *args, **options):
        created = SystemSetting.seed()
        SiteContent.load()
        self.stdout.write(f"settings_created={created}")
