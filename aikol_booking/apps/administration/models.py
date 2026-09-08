"""System settings and editable site content.

Business rules live here, not in the code, so that AIKOL can change a limit
without a software release. The confirmed values in `DEFAULTS` are defaults, not
constants.
"""

from __future__ import annotations

from django.db import models


class SystemSetting(models.Model):
    key = models.SlugField(max_length=60, unique=True)
    value = models.CharField(max_length=255)
    description = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Confirmed by AIKOL. The source decision is named so that nobody changes
    #: one of these believing it was an arbitrary choice.
    DEFAULTS: dict[str, tuple[str, str]] = {
        "advance_booking_limit_days": ("90", "How far ahead a booking may be made (decision 7)"),
        "maximum_booking_minutes": ("540", "Longest single booking, nine hours (decision 8)"),
        "bookable_window_start": ("08:00", "Earliest bookable time (decision 9)"),
        "bookable_window_end": ("22:00", "Latest bookable time (decision 9)"),
        "cancellation_cutoff_hours": ("72", "Notice a user must give, three days (decisions 12, 13)"),
        "cancellation_reason_required": ("1", "A reason is mandatory (follow-up decision)"),
        "allow_user_cancel_approved": ("1", "A user may cancel their own approved booking (decision 12)"),
        "booking_retention_years": ("7", "How long booking records are kept (decision 19)"),
        "retention_disposal_action": ("EXPORT", "Expired records are exported, not deleted (decision 20)"),
        "maximum_vehicle_trip_days": ("7", "Longest vehicle trip; to be confirmed by AIKOL"),
        "maximum_series_occurrences": ("60", "Guard on a single recurring request"),
    }

    class Meta:
        ordering = ("key",)

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str:
        row = cls.objects.filter(key=key).values_list("value", flat=True).first()
        if row is not None:
            return row
        if default is not None:
            return default
        return cls.DEFAULTS[key][0]

    @classmethod
    def get_int(cls, key: str, default: int | None = None) -> int:
        return int(cls.get(key, None if default is None else str(default)))

    @classmethod
    def get_bool(cls, key: str, default: bool | None = None) -> bool:
        raw = cls.get(key, None if default is None else ("1" if default else "0"))
        return raw in ("1", "true", "True", "yes")

    @classmethod
    def seed(cls) -> int:
        """Create any missing setting at its confirmed default. Idempotent, so
        it is safe to run on every deployment."""
        created = 0
        for key, (value, description) in cls.DEFAULTS.items():
            _, made = cls.objects.get_or_create(
                key=key, defaults={"value": value, "description": description}
            )
            created += int(made)
        return created


class SiteContent(models.Model):
    """Header and footer wording — content, not code.

    An administrator changes the Kulliyyah's address or telephone number without
    a software release, exactly as they change a booking limit. A single row;
    `load()` is the only way to reach it.
    """

    site_name = models.CharField(max_length=80, default="Room and Vehicle Booking")
    subtitle = models.CharField(
        max_length=120, default="Ahmad Ibrahim Kulliyyah of Laws · IIUM"
    )
    organisation = models.CharField(max_length=120, default="Ahmad Ibrahim Kulliyyah of Laws")
    logo = models.ImageField(upload_to="site/", blank=True)
    logo_alt = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    contact_heading = models.CharField(max_length=60, default="Booking enquiries")
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    office_hours = models.CharField(max_length=80, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "site content"

    def __str__(self) -> str:
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteContent":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
