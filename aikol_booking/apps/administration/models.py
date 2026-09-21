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

    #: Confirmed by AIKOL; CLAUDE.md section 6 names the decision behind each
    #: value so nobody changes one believing it was arbitrary. The wording here
    #: is for the administrator reading the screen, not for the record.
    DEFAULTS: dict[str, tuple[str, str]] = {
        "advance_booking_limit_days": (
            "90", "How many days ahead a booking may be made. 90 is three months."
        ),
        "maximum_booking_minutes": (
            "540", "Longest single booking, in minutes. 540 is nine hours."
        ),
        "bookable_window_start": ("08:00", "Earliest time a booking may start."),
        "bookable_window_end": ("22:00", "Latest time a booking may end."),
        "cancellation_cutoff_hours": (
            "72",
            "How many hours before the start a user may still cancel. 72 is three days. "
            "The office is not bound by this.",
        ),
        "cancellation_reason_required": (
            "1", "1 means a reason must be given when cancelling. 0 makes it optional."
        ),
        "allow_user_cancel_approved": (
            "1",
            "1 lets a user cancel their own booking after it is approved. "
            "0 limits them to bookings still awaiting a decision.",
        ),
        "booking_retention_years": (
            "7", "How many years booking records are kept before they can be exported and removed."
        ),
        "retention_disposal_action": (
            "EXPORT",
            "What happens to records past retention. EXPORT writes them to a file before removing them.",
        ),
        "maximum_vehicle_trip_days": ("7", "Longest vehicle trip, in days."),
        "maximum_series_occurrences": (
            "60", "Most bookings one weekly request may create. A semester is about 14 to 20."
        ),
    }

    #: Plain names for the settings screen; the key stays the identifier.
    LABELS: dict[str, str] = {
        "advance_booking_limit_days": "Book ahead limit",
        "maximum_booking_minutes": "Longest booking",
        "bookable_window_start": "Day starts",
        "bookable_window_end": "Day ends",
        "cancellation_cutoff_hours": "Cancellation notice",
        "cancellation_reason_required": "Reason to cancel",
        "allow_user_cancel_approved": "Cancel after approval",
        "booking_retention_years": "Keep records for",
        "retention_disposal_action": "After retention",
        "maximum_vehicle_trip_days": "Longest vehicle trip",
        "maximum_series_occurrences": "Weekly request cap",
    }

    class Meta:
        ordering = ("key",)

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"

    @property
    def label(self) -> str:
        return self.LABELS.get(self.key, self.key.replace("_", " ").capitalize())

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

    site_name = models.CharField(max_length=80, default="Venue and Vehicle Booking")
    subtitle = models.CharField(
        max_length=120, default="Ahmad Ibrahim Kulliyyah of Laws, IIUM"
    )
    organisation = models.CharField(max_length=120, default="Ahmad Ibrahim Kulliyyah of Laws")
    logo = models.ImageField(upload_to="site/", blank=True)
    logo_alt = models.CharField(max_length=200, blank=True)
    iium_logo = models.ImageField(upload_to="site/", blank=True)
    iium_logo_alt = models.CharField(
        max_length=200,
        default="International Islamic University Malaysia",
    )
    login_image = models.ImageField(upload_to="site/", blank=True)
    home_image = models.ImageField(upload_to="site/", blank=True)
    login_intro_heading = models.CharField(
        max_length=120,
        default="Venue and Vehicle Booking System",
    )
    login_intro = models.TextField(
        default=(
            "Check availability, request an AIKOL venue or Kulliyyah vehicle, "
            "and follow every decision in one place."
        )
    )
    login_points = models.TextField(
        default=(
            "See current availability for venues and vehicles\n"
            "Submit requests without a paper form\n"
            "Keep booking decisions and key handovers together"
        ),
        help_text="One short point per line.",
    )
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

    @property
    def login_point_list(self) -> list[str]:
        return [point.strip() for point in self.login_points.splitlines() if point.strip()]

    @classmethod
    def load(cls) -> "SiteContent":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Announcement(models.Model):
    """A dated notice shown immediately after the booking search.

    Announcements are deactivated rather than deleted so the office can see
    what was previously communicated and reactivate it when appropriate.
    """

    class Tone(models.TextChoices):
        INFORMATION = "INFORMATION", "Information"
        IMPORTANT = "IMPORTANT", "Important"

    title = models.CharField(max_length=120)
    message = models.TextField()
    tone = models.CharField(
        max_length=20,
        choices=Tone.choices,
        default=Tone.INFORMATION,
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_active", "-created_at")

    def __str__(self) -> str:
        return self.title
