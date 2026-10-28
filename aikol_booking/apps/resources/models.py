"""Resources: one table, extended by venues and vehicles.

A venue and a car differ in their attributes but are identical in what matters:
a thing reserved for a period, requiring approval, with keys handed over, that
must never be double-booked. `Booking.resource` points here, so there is ONE
conflict rule, ONE exclusion constraint and ONE set of conflict tests.

Django's multi-table inheritance gives exactly this shape: a `resources` row per
resource, plus a `venues` or `vehicles` row carrying the extra columns.
"""

from __future__ import annotations

import re

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
        # display_order alone ties before the first reorder; name breaks it, so
        # a page boundary is stable.
        ordering = ("display_order", "name")
        verbose_name_plural = "facilities"

    def __str__(self) -> str:
        return self.name


class VenueType(models.Model):
    """A kind of room, maintained by the Admin.

    This was a fixed list in code. The office needed to add and rename types,
    so it became a table, keyed the same way as `Facility`: `code` is the
    stable identity that CSV imports and saved filter links use, and `name` is
    the label, free to edit. The six original codes are seeded by migration,
    which is why `Venue.VenueType` still names them for code and tests.
    """

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=60)
    is_active = models.BooleanField(default=True)
    is_seeded = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Building(models.Model):
    """A building venues are in, maintained by the Admin.

    The venue list groups rooms by building and the home search filters by it.
    It used to be read out of each venue's free-text location, where
    "Level 3, AIKOL Main Building" and "AIKOL Main Building" were two places.
    """

    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self) -> str:
        return self.name

    @staticmethod
    def name_from_location(location: str) -> str:
        """"Level 3, AIKOL Main Building" -> "AIKOL Main Building"."""
        parts = [part.strip() for part in (location or "").split(",") if part.strip()]
        if len(parts) > 1 and re.match(r"^(level|floor|aras|tingkat)\b", parts[0], re.I):
            parts = parts[1:]
        return ", ".join(parts)[:80]

    @classmethod
    def for_location(cls, location: str) -> "Building | None":
        name = cls.name_from_location(location)
        if not name:
            return None
        building = cls.objects.filter(name__iexact=name).first()
        return building or cls.objects.create(name=name)


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

    # Which placeholder drawing stands in until the Kulliyyah supplies a real
    # photograph (decision 26). These are the prototype's own illustrations,
    # served from static/ — they are NOT uploads, so the rule that user-supplied
    # SVG is refused is untouched. A resource with a real photograph ignores
    # this entirely.
    image_slug = models.SlugField(
        max_length=40,
        blank=True,
        help_text="Placeholder drawing used when no photograph has been uploaded.",
    )
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

    @property
    def placeholder(self) -> str:
        """The static stand-in drawing until an administrator uploads a photograph."""
        return f"images/placeholders/{self._placeholder_slug()}.svg"

    def _placeholder_slug(self) -> str:
        # Historical imports may not have set image_slug. Keep those records
        # illustrated as well; a real uploaded photograph always takes priority.
        return self.image_slug or (
            "car-saga" if self.resource_type == ResourceType.VEHICLE else "conference"
        )

    def placeholder_variant(self, number: int) -> str:
        """View 2, 3 or 4 of the same room, for the detail gallery."""
        suffix = "" if number <= 1 else f"-v{number}"
        return f"images/placeholders/{self._placeholder_slug()}{suffix}.svg"


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
        """The seeded type codes. The live list is the `VenueType` table."""

        MOOT_COURT = "MOOT_COURT", "Moot court"
        SEMINAR = "SEMINAR", "Seminar room"
        MEETING = "MEETING", "Meeting room"
        LECTURE = "LECTURE", "Lecture room"
        DISCUSSION = "DISCUSSION", "Discussion room"
        CONFERENCE = "CONFERENCE", "Conference room"

    class Meta:
        # Meta.ordering is NOT inherited from Resource under multi-table
        # inheritance. Without this the list views paginate an unordered
        # queryset, which can repeat or skip rows between pages.
        ordering = ("display_order", "name")

    # Keyed by code and stored in the same column as before, so existing rows
    # and every `venue_type_id="SEMINAR"` keep their meaning. PROTECT: a type
    # in use is deactivated, never deleted out from under a room.
    venue_type = models.ForeignKey(
        "resources.VenueType",
        to_field="code",
        db_column="venue_type",
        on_delete=models.PROTECT,
        related_name="venues",
    )
    # Set by the administrator's ordering screen, never typed. The public and
    # office venue lists use this before name so the office can present rooms
    # in the order that makes sense to its users.
    display_order = models.PositiveIntegerField(default=0)
    # PROTECT: a building with rooms in it is hidden, never deleted. Null only
    # for the moment between an import row and save(), which fills it in.
    building = models.ForeignKey(
        Building, on_delete=models.PROTECT, related_name="venues", null=True, blank=True
    )
    location = models.CharField(max_length=120)
    floor = models.CharField(max_length=30, blank=True)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    opens_at = models.TimeField(default="08:00")
    closes_at = models.TimeField(default="22:00")

    def _placeholder_slug(self) -> str:
        if self.image_slug:
            return self.image_slug
        return {
            self.VenueType.MOOT_COURT: "moot-court",
            self.VenueType.SEMINAR: "seminar-a",
            self.VenueType.MEETING: "meeting-a",
            self.VenueType.LECTURE: "lecture",
            self.VenueType.DISCUSSION: "discussion",
            self.VenueType.CONFERENCE: "conference",
        }.get(self.venue_type_id, "conference")

    def get_venue_type_display(self) -> str:
        # Kept under the name the choices field gave it, which templates,
        # exports and the card subtitle already use.
        return self.venue_type.name if self.venue_type_id else ""

    @property
    def card_subtitle(self) -> str:
        return f"{self.get_venue_type_display()}, {self.location}, seats {self.capacity}"

    def save(self, *args, **kwargs):
        self.resource_type = ResourceType.VENUE
        # CSV imports and older scripts give only a location; the building is
        # read from it so no room is left out of the building groups.
        if self.building_id is None and self.location:
            self.building = Building.for_location(self.location)
        super().save(*args, **kwargs)


class Vehicle(Resource):
    """A Kulliyyah car.

    Cars only in the first release. `vehicle_class` exists so that adding a van
    or a bus later is a row, not a migration of the booking rules.
    """

    class Transmission(models.TextChoices):
        AUTOMATIC = "AUTO", "Automatic"
        MANUAL = "MANUAL", "Manual"

    class Meta:
        ordering = ("name",)      # not inherited; see the note on Venue

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

    def _placeholder_slug(self) -> str:
        if self.image_slug:
            return self.image_slug
        model_name = self.model.lower()
        for name in ("saga", "bezza", "innova", "exora"):
            if name in model_name:
                return f"car-{name}"
        return "car-saga"

    @property
    def card_subtitle(self) -> str:
        return (
            f"{self.make} {self.model} {self.year}, {self.seats} seats, "
            f"{self.get_transmission_display()}, {self.registration_number}"
        )

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
