"""Bookings, recurrence, key custody and the academic calendar.

The one rule this whole application exists to keep:

    new_start < existing_end  AND  new_end > existing_start

counting only bookings that are PENDING or APPROVED. Adjacent bookings
(10:00-12:00 then 12:00-14:00) do not conflict — the comparison is strict.

Because start_at and end_at are timestamps rather than a date plus two times,
that one rule covers a two-hour seminar slot and a three-day outstation car trip
with no special case.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.resources.models import Resource


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"
    COMPLETED = "COMPLETED", "Completed"


#: The statuses that reserve a resource. Rejected and cancelled bookings hold
#: nothing — this tuple is the definition of "blocking" everywhere.
BLOCKING_STATUSES = (BookingStatus.PENDING, BookingStatus.APPROVED)


class DriverArrangement(models.TextChoices):
    """Who drives, which is not the same question as who books.

    Anyone may request a car. A student may never drive a Kulliyyah car, so a
    student's booking must request a VMU driver.
    """

    SELF_DRIVE = "SELF", "Self-drive"
    VMU_DRIVER = "VMU", "Driver supplied by the Vehicle Management Unit"


class AcademicTerm(models.Model):
    """A semester. Several exist at once, and they must not overlap.

    The Kulliyyah plans next semester while the current one is still running, so
    holding a single term would make next semester's timetable unenterable until
    this one ended.

    Overlap is forbidden because `for_date()` — "which semester is this date
    in?" — has to have exactly one answer. A date in two terms would make the
    recurrence generator's behaviour arbitrary. Enforced by an exclusion
    constraint in production; validated in the form either way.
    """

    name = models.CharField(max_length=60, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ("start_date",)
        indexes = [models.Index(fields=["start_date"])]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "Teaching must end after it starts."})
        clash = (
            AcademicTerm.objects.exclude(pk=self.pk)
            .filter(start_date__lte=self.end_date, end_date__gte=self.start_date)
            .first()
        )
        if clash:
            raise ValidationError(
                f"These dates overlap {clash.name} "
                f"({clash.start_date:%d %b %Y} to {clash.end_date:%d %b %Y}). "
                "A date must belong to one semester only."
            )

    @classmethod
    def for_date(cls, day: dt.date) -> "AcademicTerm | None":
        return cls.objects.filter(start_date__lte=day, end_date__gte=day).first()

    @classmethod
    def current(cls) -> "AcademicTerm | None":
        """The term to offer by default: the one running today, else the next
        due to begin, else the most recent. Never None while any term exists —
        a form with no default selection is a form that silently does nothing."""
        today = timezone.localdate()
        return (
            cls.for_date(today)
            or cls.objects.filter(start_date__gt=today).order_by("start_date").first()
            or cls.objects.order_by("-start_date").first()
        )

    def exclusion_for(self, day: dt.date) -> str:
        """Why `day` cannot carry a class in this term. '' when it can."""
        if day < self.start_date:
            return "before the semester begins"
        if day > self.end_date:
            return "after the semester ends"
        brk = self.breaks.filter(start_date__lte=day, end_date__gte=day).first()
        return brk.name.lower() if brk else ""


class TermBreak(models.Model):
    """A break has a start, an end and a name of its own, so it is a row."""

    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name="breaks")
    name = models.CharField(max_length=60)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ("start_date",)

    def __str__(self) -> str:
        return self.name


class BookingSeries(models.Model):
    """The recurrence definition.

    Every occurrence is a real `Booking` row pointing back here. Occurrences are
    never computed on the fly: a booking that does not exist as a row cannot
    participate in the exclusion constraint, and the no-double-booking guarantee
    would collapse for exactly the bookings most likely to clash.
    """

    resource = models.ForeignKey(Resource, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    term = models.ForeignKey(AcademicTerm, on_delete=models.SET_NULL, null=True, blank=True)
    # {"0": ["09:00", "11:00"], "3": ["14:00", "16:00"]} — weekday index to
    # times. Each day keeps its own times: a course may meet Monday morning and
    # Thursday afternoon, and forcing one pair of times on both would be wrong.
    weekday_times = models.JSONField(default=dict)
    starts_on = models.DateField()
    repeat_until = models.DateField()
    purpose = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "booking series"

    def __str__(self) -> str:
        return f"Series {self.pk} · {self.resource}"


class Booking(models.Model):
    """One reservation of one resource for one period."""

    booking_reference = models.CharField(max_length=20, unique=True, editable=False)

    # PROTECT throughout. Users and resources are deactivated, never deleted,
    # while history references them; the database refuses rather than the view.
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="bookings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
        help_text="The person the booking is for.",
    )
    # Distinct from `user` so that a booking made by an administrator on
    # someone's behalf (decision 14) is honestly attributed to both.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings_created",
    )
    series = models.ForeignKey(
        BookingSeries, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
    )

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    status = models.CharField(
        max_length=10, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )
    purpose = models.TextField(help_text="Visible to the requester and on the record.")

    # Venue-only
    attendees = models.PositiveIntegerField(null=True, blank=True)

    # Vehicle-only
    driver_arrangement = models.CharField(
        max_length=5, choices=DriverArrangement.choices, blank=True
    )
    driver_name = models.CharField(max_length=150, blank=True)
    driver_contact = models.CharField(max_length=20, blank=True)
    location_from = models.CharField(max_length=150, blank=True)
    location_to = models.CharField(max_length=150, blank=True)
    passengers = models.PositiveIntegerField(null=True, blank=True)
    # A VMU booking carries TWO approvals: the ordinary booking approval by the
    # Kulliyyah office, and Kulliyyah management approval to use the car with a
    # VMU driver. The system records both; it does not merge them.
    management_approved = models.BooleanField(default=False)
    management_approved_at = models.DateTimeField(null=True, blank=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bookings_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_at",)
        indexes = [
            models.Index(fields=["resource", "start_at"]),
            models.Index(fields=["user", "-start_at"]),
            models.Index(fields=["status", "start_at"]),
            models.Index(fields=["start_at"]),
            models.Index(fields=["series"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="booking_ends_after_it_starts",
            )
        ]

    def __str__(self) -> str:
        return f"{self.booking_reference} · {self.resource.name}"

    # -- Derived ---------------------------------------------------------

    @property
    def duration(self) -> dt.timedelta:
        return self.end_at - self.start_at

    @property
    def is_blocking(self) -> bool:
        return self.status in BLOCKING_STATUSES

    @property
    def is_multi_day(self) -> bool:
        return timezone.localtime(self.start_at).date() != timezone.localtime(self.end_at).date()

    def can_be_cancelled_by(self, user) -> bool:
        """Decision 12: a user cancels their OWN booking freely, up to three
        days before. Administrators and approvers are not bound by the cutoff —
        they are the people who handle the exceptions."""
        if self.status not in BLOCKING_STATUSES:
            return False
        if user.is_approver:
            return True
        if user != self.user:
            return False
        from apps.administration.models import SystemSetting

        hours = SystemSetting.get_int("cancellation_cutoff_hours", 72)
        return timezone.now() <= self.start_at - dt.timedelta(hours=hours)

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = self._next_reference()
        super().save(*args, **kwargs)

    def _next_reference(self) -> str:
        stamp = timezone.localtime(self.start_at or timezone.now()).strftime("%Y%m")
        prefix = f"BK-{stamp}-"
        last = (
            Booking.objects.filter(booking_reference__startswith=prefix)
            .order_by("-booking_reference")
            .values_list("booking_reference", flat=True)
            .first()
        )
        nxt = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{nxt:04d}"


class KeyHandover(models.Model):
    """Key issue and return, per booking (decision 17).

    Four people can be involved and they are frequently not the same person: who
    booked it, who collected the key, who issued it, and who took it back. The
    booking already records the first; the other three are recorded here, because
    "the user who booked it" is not who turned up at the office.
    """

    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="key_handover")

    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="keys_issued",
    )
    collected_by_name = models.CharField(
        max_length=150, blank=True, help_text="Who physically collected the key."
    )
    collected_by_contact = models.CharField(max_length=20, blank=True)

    returned_at = models.DateTimeField(null=True, blank=True)
    returned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="keys_received",
    )
    returned_by_name = models.CharField(max_length=150, blank=True)
    condition_notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Key for {self.booking.booking_reference}"

    @property
    def state(self) -> str:
        if self.returned_at:
            return "Returned"
        if self.issued_at:
            overdue = timezone.now() > self.booking.end_at
            return "Overdue" if overdue else "Issued"
        return "Awaiting collection"


class BookingArchive(models.Model):
    """A denormalised copy of a booking, kept when the archive disposal action
    is chosen instead of export.

    NO foreign keys, deliberately. The point of an archive row is to outlive the
    live tables: it holds the email, the name and the resource code as text, so
    it stays readable after the user is renamed, the resource is deleted, or the
    booking itself is gone. A foreign key would either block the deletion it
    exists to permit, or dangle.
    """

    booking_reference = models.CharField(max_length=20, db_index=True)
    user_email = models.EmailField()
    user_name = models.CharField(max_length=150)
    resource_code = models.CharField(max_length=30)
    resource_name = models.CharField(max_length=120)
    resource_type = models.CharField(max_length=10)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(max_length=10)
    purpose = models.TextField(blank=True)
    key_issued_at = models.DateTimeField(null=True, blank=True)
    key_returned_at = models.DateTimeField(null=True, blank=True)
    original_created_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-start_at",)
        indexes = [models.Index(fields=["start_at"])]

    def __str__(self) -> str:
        return f"{self.booking_reference} (archived)"

    @classmethod
    def from_booking(cls, booking: "Booking") -> "BookingArchive":
        handover = getattr(booking, "key_handover", None)
        return cls(
            booking_reference=booking.booking_reference,
            user_email=booking.user.email,
            user_name=booking.user.full_name,
            resource_code=booking.resource.code,
            resource_name=booking.resource.name,
            resource_type=booking.resource.resource_type,
            start_at=booking.start_at,
            end_at=booking.end_at,
            status=booking.status,
            purpose=booking.purpose,
            key_issued_at=handover.issued_at if handover else None,
            key_returned_at=handover.returned_at if handover else None,
            original_created_at=booking.created_at,
        )
