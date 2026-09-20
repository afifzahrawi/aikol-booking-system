# The header subtitle separated the Kulliyyah from the university with a
# middle dot, and the seeded office hours used dashes. Ordinary words and
# punctuation say the same thing. Rows still
# carrying the old default are brought along; anything an administrator has
# edited is left as they wrote it.
from django.db import migrations, models

OLD = "Ahmad Ibrahim Kulliyyah of Laws · IIUM"
NEW = "Ahmad Ibrahim Kulliyyah of Laws, IIUM"
OLD_HOURS = "Mon–Fri, 08:30–17:00"
NEW_HOURS = "Monday to Friday, 08:30 to 17:00"


def forwards(apps, schema_editor):
    SiteContent = apps.get_model("administration", "SiteContent")
    SiteContent.objects.filter(subtitle=OLD).update(subtitle=NEW)
    SiteContent.objects.filter(office_hours=OLD_HOURS).update(office_hours=NEW_HOURS)


def backwards(apps, schema_editor):
    SiteContent = apps.get_model("administration", "SiteContent")
    SiteContent.objects.filter(subtitle=NEW).update(subtitle=OLD)
    SiteContent.objects.filter(office_hours=NEW_HOURS).update(office_hours=OLD_HOURS)


class Migration(migrations.Migration):
    dependencies = [("administration", "0003_venue_vehicle_wording")]

    operations = [
        migrations.AlterField(
            model_name="sitecontent",
            name="subtitle",
            field=models.CharField(default=NEW, max_length=120),
        ),
        migrations.RunPython(forwards, backwards),
    ]
