from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="EmailConfiguration",
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
                ("host", models.CharField(blank=True, max_length=255)),
                ("port", models.PositiveIntegerField(default=587)),
                ("username", models.CharField(blank=True, max_length=255)),
                ("encrypted_password", models.TextField(blank=True, editable=False)),
                ("use_tls", models.BooleanField(default=True)),
                ("use_ssl", models.BooleanField(default=False)),
                (
                    "default_from_email",
                    models.CharField(
                        default="AIKOL Booking <booking-aikol@iium.edu.my>",
                        max_length=255,
                    ),
                ),
                ("timeout_seconds", models.PositiveIntegerField(default=20)),
                ("is_active", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "email delivery configuration",
                "verbose_name_plural": "email delivery configuration",
            },
        )
    ]
