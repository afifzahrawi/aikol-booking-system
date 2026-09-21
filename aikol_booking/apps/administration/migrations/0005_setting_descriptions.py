# The settings screen described each rule by the number of the AIKOL decision
# behind it ("decision 7"), which means nothing to the administrator reading
# it. Descriptions are not editable on the screen, so every known key is
# simply brought up to the current wording in the model.
from django.db import migrations


def forwards(apps, schema_editor):
    from apps.administration.models import SystemSetting as Current

    SystemSetting = apps.get_model("administration", "SystemSetting")
    for key, (_, description) in Current.DEFAULTS.items():
        SystemSetting.objects.filter(key=key).update(description=description)


class Migration(migrations.Migration):
    dependencies = [("administration", "0004_subtitle_wording")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
