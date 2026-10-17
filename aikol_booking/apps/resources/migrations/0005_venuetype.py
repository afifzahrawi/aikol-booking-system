"""Venue types become a table the Admin maintains.

The column keeps its name and its values: the six codes are seeded first, then
the column becomes a foreign key to `VenueType.code`. No venue row changes.
"""

import django.db.models.deletion
from django.db import migrations, models

SEEDED = [
    ("MOOT_COURT", "Moot court"),
    ("SEMINAR", "Seminar room"),
    ("MEETING", "Meeting room"),
    ("LECTURE", "Lecture room"),
    ("DISCUSSION", "Discussion room"),
    ("CONFERENCE", "Conference room"),
]


def seed(apps, schema_editor):
    VenueType = apps.get_model("resources", "VenueType")
    Venue = apps.get_model("resources", "Venue")
    for code, name in SEEDED:
        VenueType.objects.get_or_create(code=code, defaults={"name": name, "is_seeded": True})
    # Any code already in use that the list above does not know becomes a type
    # of its own, so the foreign key never finds an orphan.
    for code in Venue.objects.values_list("venue_type", flat=True).distinct():
        if code:
            VenueType.objects.get_or_create(
                code=code, defaults={"name": code.replace("_", " ").capitalize()}
            )


class Migration(migrations.Migration):
    dependencies = [
        ("resources", "0004_venue_display_order"),
    ]

    operations = [
        migrations.CreateModel(
            name="VenueType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=60)),
                ("is_active", models.BooleanField(default=True)),
                ("is_seeded", models.BooleanField(default=False)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="venue",
            name="venue_type",
            field=models.ForeignKey(
                db_column="venue_type",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="venues",
                to="resources.venuetype",
                to_field="code",
            ),
        ),
    ]
