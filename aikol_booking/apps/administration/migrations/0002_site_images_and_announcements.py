from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitecontent",
            name="home_image",
            field=models.ImageField(blank=True, upload_to="site/"),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="iium_logo",
            field=models.ImageField(blank=True, upload_to="site/"),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="iium_logo_alt",
            field=models.CharField(
                default="International Islamic University Malaysia",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="login_image",
            field=models.ImageField(blank=True, upload_to="site/"),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="login_intro",
            field=models.TextField(
                default=(
                    "Check availability, request an AIKOL venue or Kulliyyah vehicle, "
                    "and follow every decision in one place."
                )
            ),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="login_intro_heading",
            field=models.CharField(
                default="Room and Vehicle Booking System",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="login_points",
            field=models.TextField(
                default=(
                    "See current availability for venues and vehicles\n"
                    "Submit requests without a paper form\n"
                    "Keep booking decisions and key handovers together"
                ),
                help_text="One short point per line.",
            ),
        ),
        migrations.CreateModel(
            name="Announcement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=120)),
                ("message", models.TextField()),
                (
                    "tone",
                    models.CharField(
                        choices=[
                            ("INFORMATION", "Information"),
                            ("IMPORTANT", "Important"),
                        ],
                        default="INFORMATION",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-is_active", "-created_at")},
        ),
    ]
