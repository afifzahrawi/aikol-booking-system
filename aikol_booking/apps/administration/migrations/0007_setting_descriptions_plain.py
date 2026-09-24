# Yes/No settings were described as "1" and "0", which the screen no longer
# shows, and several descriptions carried arithmetic the administrator does not
# need. Descriptions are not editable on the screen, so every known key is
# brought up to the current wording in the model, as 0005 did.
from django.db import migrations


def forwards(apps, schema_editor):
    from apps.administration.models import SystemSetting as Current

    SystemSetting = apps.get_model("administration", "SystemSetting")
    for key, (_, description) in Current.DEFAULTS.items():
        SystemSetting.objects.filter(key=key).update(description=description)


class Migration(migrations.Migration):
    dependencies = [("administration", "0006_logo_labels")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
