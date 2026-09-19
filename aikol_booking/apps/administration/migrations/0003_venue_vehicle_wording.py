from django.db import migrations, models


def update_default_wording(apps, schema_editor):
    SiteContent = apps.get_model("administration", "SiteContent")
    SiteContent.objects.filter(site_name="Room and Vehicle Booking").update(
        site_name="Venue and Vehicle Booking"
    )
    SiteContent.objects.filter(login_intro_heading="Room and Vehicle Booking System").update(
        login_intro_heading="Venue and Vehicle Booking System"
    )


class Migration(migrations.Migration):
    dependencies = [("administration", "0002_site_images_and_announcements")]

    operations = [
        migrations.AlterField(
            model_name="sitecontent",
            name="site_name",
            field=models.CharField(default="Venue and Vehicle Booking", max_length=80),
        ),
        migrations.AlterField(
            model_name="sitecontent",
            name="login_intro_heading",
            field=models.CharField(default="Venue and Vehicle Booking System", max_length=120),
        ),
        migrations.RunPython(update_default_wording, migrations.RunPython.noop),
    ]
