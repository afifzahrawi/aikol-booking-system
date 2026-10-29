"""Existing names to capitals, matching `User.normalise_name` for new ones.

Not reversible: the original capitalisation is not kept. The deploy backs up
the database before migrating, which is the way back if ever needed.
"""

from django.db import migrations


def to_capitals(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    changed = []
    for person in User.objects.only("id", "full_name").iterator():
        name = " ".join((person.full_name or "").split()).upper()
        if name != person.full_name:
            person.full_name = name
            changed.append(person)
    User.objects.bulk_update(changed, ["full_name"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_alter_user_email_alter_user_identification_number")]

    operations = [migrations.RunPython(to_capitals, migrations.RunPython.noop)]
