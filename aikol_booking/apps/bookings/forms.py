"""Booking forms.

Every rule these enforce is enforced again in the service layer. A form is a
courtesy to the person filling it in; it is never the only place a rule lives,
because a POST can arrive without ever rendering one.
"""

from __future__ import annotations

import datetime as dt

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from config.forms import StyledFormMixin
from django.utils import timezone

from apps.administration.models import SystemSetting
from apps.resources.models import ResourceType

from .models import AcademicTerm, DriverArrangement, TermBreak
from .services import validate_period

WEEKDAYS = [
    (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
    (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
]


class OnBehalfMixin:
    """A hidden identifier paired with the server-backed user combobox.

    A normal ModelChoiceField would render every account into one enormous
    select. The visible combobox searches the database; this hidden field still
    gives Django authoritative validation of the chosen user id.
    """

    def add_on_behalf_field(self, user) -> None:
        if not user.is_administrator:
            return
        from apps.accounts.models import User

        self.fields["on_behalf_of"] = forms.ModelChoiceField(
            required=False,
            queryset=User.objects.filter(is_active=True, email_verified=True),
            widget=forms.HiddenInput,
            label="Booking for",
        )

    @property
    def booking_for_label(self) -> str:
        from apps.accounts.models import describe_person

        if "on_behalf_of" not in self.fields:
            return ""
        raw = self["on_behalf_of"].value()
        if not raw:
            return ""
        person = self.fields["on_behalf_of"].queryset.filter(pk=raw).first()
        if not person:
            return ""
        return f"{person.full_name}, {describe_person(person)}"


QUARTER_MINUTES = (0, 15, 30, 45)


def quarter_hour(value):
    """Refuse a time that is not on the quarter.

    `step="900"` drives the spinner arrows and nothing else: a typed 13:16 is
    accepted by the browser, and the form is rendered with novalidate anyway.
    The rule has to live here, where it cannot be bypassed, because a room
    handed over at 13:16 is a room nobody can describe in a timetable.
    """
    if value is None:
        return value
    if value.minute not in QUARTER_MINUTES or value.second or value.microsecond:
        raise forms.ValidationError(
            "Set the time on the quarter hour: %(examples)s.",
            params={"examples": f"{value.hour:02d}:00, {value.hour:02d}:15, "
                                f"{value.hour:02d}:30 or {value.hour:02d}:45"},
        )
    return value


class TimeOnTheQuarterField(forms.TimeField):
    """A time field that only accepts :00, :15, :30 and :45."""

    def __init__(self, *args, **kwargs):
        attrs = {"type": "time", "step": 900}
        attrs.update(kwargs.pop("attrs", {}))
        kwargs.setdefault("widget", forms.TimeInput(attrs=attrs))
        super().__init__(*args, **kwargs)

    def clean(self, value):
        return quarter_hour(super().clean(value))


class BookingForm(OnBehalfMixin, StyledFormMixin, forms.Form):
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


    start_date = forms.DateField(
        label="Start Date", widget=forms.DateInput(attrs={"type": "date"})
    )
    start_time = TimeOnTheQuarterField(label="Start Time")
    end_date = forms.DateField(
        required=False,
        label="End Date",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Vehicles only. Leave blank for a same-day trip.",
    )
    end_time = TimeOnTheQuarterField(label="End Time")
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Visible to the requester and on the record.",
    )

    # Venue only
    attendees = forms.IntegerField(required=False, min_value=1, label="Number of Attendees")

    # Vehicle only
    driver_arrangement = forms.ChoiceField(
        required=False,
        choices=DriverArrangement.choices,
        widget=forms.RadioSelect,
    )
    location_from = forms.CharField(required=False, max_length=150, label="Location From")
    location_to = forms.CharField(required=False, max_length=150, label="Location To")
    passengers = forms.IntegerField(required=False, min_value=1, label="Number of Passengers")

    def __init__(self, *args, resource, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource = resource
        self.user = user
        self.is_vehicle = resource.resource_type == ResourceType.VEHICLE

        self.add_on_behalf_field(user)

        for name in ("attendees",) if self.is_vehicle else (
            "driver_arrangement", "location_from", "location_to", "passengers", "end_date"
        ):
            self.fields.pop(name, None)

        if not self.is_vehicle:
            # A room is booked for one day, so there is one date and a pair of
            # times. "Start Date" only makes sense beside an end date, which a
            # room does not have, and the two times belong side by side.
            self.fields["start_date"].label = "Date"
            self.layout = [["start_date"], ["start_time", "end_time"]]

        if self.is_vehicle:
            self.fields["driver_arrangement"].required = True
            self.fields["location_from"].required = True
            self.fields["location_to"].required = True
            self.fields["passengers"].required = True
            self.fields["driver_arrangement"].choices = [
                (DriverArrangement.VMU_DRIVER, DriverArrangement.VMU_DRIVER.label)
            ]
            self.fields["driver_arrangement"].widget = forms.HiddenInput()
            self.fields["driver_arrangement"].initial = DriverArrangement.VMU_DRIVER
        else:
            self.fields["attendees"].required = True
            self.fields["attendees"].help_text = f"The venue seats {resource.capacity}."

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

        if self.is_vehicle:
            arrangement = cleaned.get("driver_arrangement")
            if arrangement != DriverArrangement.VMU_DRIVER:
                self.add_error(
                    "driver_arrangement",
                    "Kulliyyah vehicles must use a driver supplied by the Vehicle Management Unit.",
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


class RecurrenceForm(OnBehalfMixin, StyledFormMixin, forms.Form):
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
        label="Create the dates listed as bookable and leave out the rest",
        help_text="Tick this after reading the list below.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.add_on_behalf_field(user)
        self.fields["term"].initial = AcademicTerm.current()
        for index, label in WEEKDAYS:
            self.fields[f"day_{index}"] = forms.BooleanField(required=False, label=label)
            self.fields[f"from_{index}"] = TimeOnTheQuarterField(required=False)
            self.fields[f"to_{index}"] = TimeOnTheQuarterField(required=False)

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


class VehicleManagementDecisionForm(StyledFormMixin, forms.Form):
    """Assign the VMU driver and record the separately attributed decision."""

    layout = [["driver_name", "driver_contact"]]

    driver_name = forms.CharField(
        required=False,
        max_length=150,
        help_text="Required when management approves the trip.",
    )
    driver_contact = forms.CharField(
        required=False,
        max_length=20,
        help_text="Required when management approves the trip.",
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Required when management does not approve the trip.",
    )

    def clean(self):
        cleaned = super().clean()
        action = self.data.get("action")
        if action == "approve":
            if not (cleaned.get("driver_name") or "").strip():
                self.add_error("driver_name", "Assign the VMU driver before approving.")
            if not (cleaned.get("driver_contact") or "").strip():
                self.add_error("driver_contact", "Give the driver's contact number.")
        elif action == "reject":
            if len((cleaned.get("reason") or "").strip()) < 5:
                self.add_error("reason", "Give a usable reason for not approving the trip.")
        else:
            self.add_error(None, "Choose approve or do not approve.")
        return cleaned


class AcademicTermForm(StyledFormMixin, forms.ModelForm):
    layout = [["start_date", "end_date"]]

    class Meta:
        model = AcademicTerm
        fields = ("name", "start_date", "end_date")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class TermBreakForm(StyledFormMixin, forms.ModelForm):
    layout = [["start_date", "end_date"]]

    class Meta:
        model = TermBreak
        fields = ("name", "start_date", "end_date")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class BaseTermBreakFormSet(BaseInlineFormSet):
    """Validate break rows together, including rows not saved yet.

    ``TermBreak.clean()`` catches collisions with rows already in the database.
    A formset can also contain two new rows, so it must check its own cleaned
    forms before either row is written.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        periods: list[tuple[dt.date, dt.date, str]] = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            start = form.cleaned_data.get("start_date")
            end = form.cleaned_data.get("end_date")
            if not start or not end:
                continue
            name = form.cleaned_data.get("name") or "another break"
            for other_start, other_end, other_name in periods:
                if start <= other_end and end >= other_start:
                    raise forms.ValidationError(
                        f"{name} overlaps {other_name}. Break dates in one calendar "
                        "must not overlap."
                    )
            periods.append((start, end, name))


TermBreakFormSet = inlineformset_factory(
    AcademicTerm,
    TermBreak,
    form=TermBreakForm,
    formset=BaseTermBreakFormSet,
    extra=1,
    can_delete=True,
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
