"""Booking forms.

Every rule these enforce is enforced again in the service layer. A form is a
courtesy to the person filling it in; it is never the only place a rule lives,
because a POST can arrive without ever rendering one.
"""

from __future__ import annotations

import datetime as dt

from django import forms

from config.forms import StyledFormMixin
from django.utils import timezone

from apps.administration.models import SystemSetting
from apps.resources.models import ResourceType

from .models import AcademicTerm, DriverArrangement
from .services import check_driver_arrangement, validate_period

WEEKDAYS = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
    (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class BookingForm(StyledFormMixin, forms.Form):
    """One form for both kinds of resource.

    The fields differ — a room needs an attendee count, a car needs a
    destination and a driver arrangement — but the period, the purpose and the
    conflict check are identical, so they are written once.
    """
    layout = [
        ["start_date", "start_time"],
        ["end_date", "end_time"],
        ["location_from", "location_to"],
        ["attendees", "passengers"],
    ]


    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Vehicles only. Leave blank for a same-day trip.",
    )
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Visible to the requester and on the record.",
    )

    # Venue only
    attendees = forms.IntegerField(required=False, min_value=1)

    # Vehicle only
    driver_arrangement = forms.ChoiceField(
        required=False,
        choices=DriverArrangement.choices,
        widget=forms.RadioSelect,
    )
    location_from = forms.CharField(required=False, max_length=150)
    location_to = forms.CharField(required=False, max_length=150)
    passengers = forms.IntegerField(required=False, min_value=1)

    def __init__(self, *args, resource, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource = resource
        self.user = user
        self.is_vehicle = resource.resource_type == ResourceType.VEHICLE

        if user.is_administrator:
            # Decision 14. The booking is attributed to BOTH people: `user` is
            # who it is for, `created_by` is who made it. Merging them would
            # lose which of the two to contact and which to hold responsible.
            from apps.accounts.models import User

            self.fields["on_behalf_of"] = forms.ModelChoiceField(
                required=False,
                queryset=User.objects.filter(is_active=True, email_verified=True)
                .order_by("full_name"),
                label="Booking for",
                empty_label="Myself",
                help_text=(
                    "Leave as Myself unless you are booking for somebody else. Only "
                    "verified accounts appear here — an unverified one cannot book."
                ),
            )

        for name in ("attendees",) if self.is_vehicle else (
            "driver_arrangement", "location_from", "location_to", "passengers", "end_date"
        ):
            self.fields.pop(name, None)

        if self.is_vehicle:
            self.fields["driver_arrangement"].required = True
            self.fields["location_from"].required = True
            self.fields["location_to"].required = True
            self.fields["passengers"].required = True
            if not user.may_drive:
                # A student may never drive a Kulliyyah car. Removing the choice
                # is a courtesy; the view refuses it regardless.
                self.fields["driver_arrangement"].choices = [
                    (DriverArrangement.VMU_DRIVER, DriverArrangement.VMU_DRIVER.label)
                ]
                self.fields["driver_arrangement"].help_text = (
                    "Students may book a car but may not drive one, so a Vehicle Management "
                    "Unit driver is requested through STADD. That needs Kulliyyah management "
                    "approval as well as approval of this booking."
                )
        else:
            self.fields["attendees"].required = True
            self.fields["attendees"].help_text = f"The room seats {resource.capacity}."

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        if not (start_date and start_time and end_time):
            return cleaned

        end_date = cleaned.get("end_date") or start_date
        start_at = timezone.make_aware(dt.datetime.combine(start_date, start_time))
        end_at = timezone.make_aware(dt.datetime.combine(end_date, end_time))
        cleaned["start_at"] = start_at
        cleaned["end_at"] = end_at

        for problem in validate_period(self.resource, start_at, end_at):
            self.add_error(None, problem)

        # Eligibility to drive belongs to the person the booking is FOR, not to
        # the administrator filling the form in. An administrator who may drive
        # must not confer that on a student by typing on their behalf.
        subject = cleaned.get("on_behalf_of") or self.user

        if self.is_vehicle:
            arrangement = cleaned.get("driver_arrangement")
            for problem in check_driver_arrangement(subject, self.resource, arrangement):
                # The VMU note is guidance, not a refusal — it tells the
                # requester about the second approval before they are surprised
                # by it. Only the eligibility and licence problems block.
                if arrangement == DriverArrangement.VMU_DRIVER:
                    continue
                self.add_error("driver_arrangement", problem)
            if arrangement == DriverArrangement.SELF_DRIVE and subject.licence_expiry:
                # The licence must be valid at the END of the trip, not on the
                # day it is requested.
                if subject.licence_expiry < end_at.date():
                    self.add_error(
                        "driver_arrangement",
                        "Your licence expires before the trip ends.",
                    )
            passengers = cleaned.get("passengers")
            if passengers and passengers > self.resource.seats:
                self.add_error(
                    "passengers", f"{self.resource.name} seats {self.resource.seats}."
                )
        else:
            attendees = cleaned.get("attendees")
            if attendees and attendees > self.resource.capacity:
                self.add_error(
                    "attendees", f"{self.resource.name} seats {self.resource.capacity}."
                )
        return cleaned


class RecurrenceForm(StyledFormMixin, forms.Form):
    """A weekly series, generated against one semester.

    Each weekday keeps its own times: a course may meet Monday morning and
    Thursday afternoon, and forcing one pair of times on both would be wrong.
    """
    layout = [["starts_on", "repeat_until"]]


    term = forms.ModelChoiceField(
        queryset=AcademicTerm.objects.all(),
        help_text="Which calendar the series is generated against.",
    )
    starts_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    repeat_until = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    purpose = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    accept_partial = forms.BooleanField(
        required=False,
        label="Create the dates that are free, and leave out the ones already reserved",
        help_text=(
            "Only tick this after reading the list of clashes below. Nothing is ever "
            "dropped without being shown to you first."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["term"].initial = AcademicTerm.current()
        for index, label in WEEKDAYS:
            self.fields[f"day_{index}"] = forms.BooleanField(required=False, label=label)
            self.fields[f"from_{index}"] = forms.TimeField(
                required=False, widget=forms.TimeInput(attrs={"type": "time"})
            )
            self.fields[f"to_{index}"] = forms.TimeField(
                required=False, widget=forms.TimeInput(attrs={"type": "time"})
            )

    def weekday_rows(self):
        """The three fields for each weekday, grouped, so the template renders a
        row rather than reconstructing the grouping from field names."""
        for index, label in WEEKDAYS:
            yield {
                "label": label,
                "day": self[f"day_{index}"],
                "start": self[f"from_{index}"],
                "end": self[f"to_{index}"],
            }

    def clean(self):
        cleaned = super().clean()
        times: dict[str, list[str]] = {}
        for index, label in WEEKDAYS:
            if not cleaned.get(f"day_{index}"):
                continue
            start = cleaned.get(f"from_{index}")
            end = cleaned.get(f"to_{index}")
            if not start or not end:
                self.add_error(f"from_{index}", f"Give both times for {label}.")
                continue
            if end <= start:
                self.add_error(f"to_{index}", f"{label} ends before it starts.")
                continue
            times[str(index)] = [start.strftime("%H:%M"), end.strftime("%H:%M")]

        if not times:
            self.add_error(None, "Choose at least one day of the week.")
        cleaned["weekday_times"] = times

        starts_on = cleaned.get("starts_on")
        until = cleaned.get("repeat_until")
        if starts_on and until and until < starts_on:
            self.add_error("repeat_until", "The series ends before it starts.")

        limit = SystemSetting.get_int("advance_booking_limit_days")
        latest = timezone.localdate() + dt.timedelta(days=limit)
        if until and until > latest:
            self.add_error(
                "repeat_until",
                f"Bookings may be made up to {limit} days ahead. "
                f"The latest bookable date is {latest:%d %b %Y}.",
            )
        return cleaned


class DecisionForm(StyledFormMixin, forms.Form):
    """Approve or reject. A rejection must say why; the requester is told."""

    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Required when rejecting. Sent to the requester.",
    )


class CancellationForm(StyledFormMixin, forms.Form):
    """A reason is mandatory — confirmed follow-up decision."""

    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Reason for cancelling",
        help_text="Required, and recorded against the booking.",
    )

    def clean_reason(self) -> str:
        reason = self.cleaned_data["reason"].strip()
        if len(reason) < 5:
            raise forms.ValidationError("Give a usable reason, not a placeholder.")
        return reason
