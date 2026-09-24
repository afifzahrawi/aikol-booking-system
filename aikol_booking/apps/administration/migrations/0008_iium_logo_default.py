# The IIUM logo uploaded through Site content is the same artwork as the static
# default (static/images/iium_logo_uploaded.jpg). Clearing the upload makes the
# header use the static copy, whose fixed URL the browser caches, and leaves the
# Site content field empty for a genuinely different logo later. Only that one
# known upload is cleared; any other logo an administrator uploads is kept.
from django.db import migrations

KNOWN_UPLOAD = "site/IIUM_Logo_2019.svg.jpg"


def forwards(apps, schema_editor):
    SiteContent = apps.get_model("administration", "SiteContent")
    SiteContent.objects.filter(iium_logo=KNOWN_UPLOAD).update(iium_logo="")


class Migration(migrations.Migration):
    dependencies = [("administration", "0007_setting_descriptions_plain")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
