"""Resources: one table, extended by venues and vehicles.

A venue and a car differ in their attributes but are identical in what matters:
a thing reserved for a period, requiring approval, with keys handed over, that
must never be double-booked. `Booking.resource` points here, so there is ONE
conflict rule, ONE exclusion constraint and ONE set of conflict tests.

Django's multi-table inheritance gives exactly this shape: a `resources` row per
resource, plus a `venues` or `vehicles` row carrying the extra columns.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class ResourceType(models.TextChoices):
    VENUE = "VENUE", "Venue"
    VEHICLE = "VEHICLE", "Vehicle"


class ResourceStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    MAINTENANCE = "MAINTENANCE", "Under maintenance"


class Facility(models.Model):
    """A facility or vehicle feature, maintained by administrators.

    This was a JSON field while the list was nine values fixed in code.
    Administrators can now create facilities, and a facility they create needs a
    stored display name — an attribute of its own, which is the condition for
    normalising into a table.

    `code` is the stable identity: CSV imports and saved filter links refer to
    it and it never changes. `name` is the label, and may be edited freely. If
    the display name were also the key, correcting a spelling mistake would
    break every import template that referred to it.
    """

    class AppliesTo(models.TextChoices):
        VENUE = "VENUE", "Venues"
        VEHICLE = "VEHICLE", "Vehicles"
        BOTH = "BOTH", "Both"

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    applies_to = models.CharField(max_length=10, choices=AppliesTo.choices, default=AppliesTo.VENUE)
    # Set by dragging rows, not typed. The whole column is rewritten as 1..n in
    # one transaction on every move, so there are never gaps or ties.
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_seeded = models.BooleanField(
        default=False, help_text="Created at installation rather than by an administrator."
    )

    class Meta:
        ordering = ("display_order", "name")
        verbose_name_plural = "facilities"

    def __str__(self) -> str:
        return self.name


class Resource(models.Model):
    """The bookable thing. Never deleted once any booking refers to it."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=10, choices=ResourceType.choices)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=15, choices=ResourceStatus.choices, default=ResourceStatus.ACTIVE
    )
    # Decision 4 makes this true for every resource in the first release. The
    # field is kept because AIKOL may relax the rule; nothing ships with it off.
    approval_required = models.BooleanField(default=True)
    facilities = models.ManyToManyField(Facility, through="ResourceFacility", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        indexes = [models.Index(fields=["resource_type", "status"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def is_bookable(self) -> bool:
        """Whether the resource may be reserved at all.

        Subclasses narrow this. A vehicle adds its road tax, which withdraws the
        car without telling the requester why — that is an office matter.
        """
        return self.status == ResourceStatus.ACTIVE

    def get_absolute_url(self) -> str:
        return reverse("resources:detail", args=[self.pk])


class ResourceFacility(models.Model):
    """The join. Explicit, so the unique constraint is stated rather than implied."""

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    # A facility in use cannot be deleted out from under a resource.
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "facility"], name="unique_resource_facility"
            )
        ]


class Venue(Resource):
    """A room. Occupied within a single day, unlike a vehicle."""

    class VenueType(models.TextChoices):
        MOOT_COURT = "MOOT_COURT", "Moot court"
        SEMINAR = "SEMINAR", "Seminar room"
        MEETING = "MEETING", "Meeting room"
        LECTURE = "LECTURE", "Lecture room"
        DISCUSSION = "DISCUSSION", "Discussion room"
        CONFERENCE = "CONFERENCE", "Conference room"

    venue_type = models.CharField(max_length=20, choices=VenueType.choices)
    location = models.CharField(max_length=120)
    floor = models.CharField(max_length=30, blank=True)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    opens_at = models.TimeField(default="08:00")
    closes_at = models.TimeField(default="22:00")

    def save(self, *args, **kwargs):
        self.resource_type = ResourceType.VENUE
        super().save(*args, **kwargs)


class Vehicle(Resource):
    """A Kulliyyah car.

    Cars only in the first release. `vehicle_class` exists so that adding a van
    or a bus later is a row, not a migration of the booking rules.
    """

    class Transmission(models.TextChoices):
        AUTOMATIC = "AUTO", "Automatic"
        MANUAL = "MANUAL", "Manual"

    registration_number = models.CharField(max_length=20, unique=True)
    vehicle_class = models.CharField(max_length=20, default="CAR")
    make = models.CharField(max_length=40)
    model = models.CharField(max_length=40)
    year = models.PositiveIntegerField()
    seats = models.PositiveIntegerField(validators=[MinValueValidator(2)])
    transmission = models.CharField(
        max_length=10, choices=Transmission.choices, default=Transmission.AUTOMATIC
    )
    fuel_type = models.CharField(max_length=20, blank=True)
    # Administrator-facing only. An untaxed car is withdrawn from the booking
    # screens automatically and the requester is told the vehicle is
    # unavailable, not why — you cannot lawfully drive an untaxed car, but the
    # date itself is the office's business.
    road_tax_expiry = models.DateField()

    def save(self, *args, **kwargs):
        self.resource_type = ResourceType.VEHICLE
        super().save(*args, **kwargs)

    def road_tax_valid_on(self, day) -> bool:
        return self.road_tax_expiry >= day

    @property
    def is_bookable(self) -> bool:
        from django.utils import timezone

        return super().is_bookable and self.road_tax_valid_on(timezone.localdate())


def resource_image_path(instance: "ResourceImage", filename: str) -> str:
    """Uploads are renamed on save; the original filename is never trusted."""
    import uuid

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"resources/{instance.resource_id}/{uuid.uuid4().hex}.{suffix}"


class ResourceImage(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=resource_image_path)
    caption = models.CharField(max_length=120, blank=True)
    display_order = models.PositiveIntegerField(default=0, help_text="0 is the main image.")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("display_order", "id")
