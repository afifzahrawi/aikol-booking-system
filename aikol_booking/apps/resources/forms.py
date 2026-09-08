"""Forms for resource management."""

from __future__ import annotations

import re

from django import forms

from config.forms import StyledFormMixin

from .models import Facility, ResourceImage, ResourceStatus, Vehicle, Venue
from .validators import validate_image_upload


class FacilityChoiceMixin:
    """Offer only the facilities that apply to this kind of resource, and only
    the active ones — a deactivated facility is hidden from the forms, which is
    the whole point of deactivating it."""

    applies_to: str

    def limit_facilities(self) -> None:
        self.fields["facilities"].queryset = Facility.objects.filter(
            is_active=True, applies_to__in=[self.applies_to, Facility.AppliesTo.BOTH]
        )
        self.fields["facilities"].widget = forms.CheckboxSelectMultiple()


class VenueForm(StyledFormMixin, FacilityChoiceMixin, forms.ModelForm):
    layout = [
        ["code", "name"],
        ["location", "floor"],
        ["venue_type", "capacity"],
        ["opens_at", "closes_at"],
    ]

    applies_to = Facility.AppliesTo.VENUE

    class Meta:
        model = Venue
        fields = (
            "code", "name", "venue_type", "location", "floor", "capacity",
            "opens_at", "closes_at", "description", "facilities", "status",
        )
        widgets = {
            "opens_at": forms.TimeInput(attrs={"type": "time"}),
            "closes_at": forms.TimeInput(attrs={"type": "time"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_facilities()
        if self.instance.pk:
            # The code is the stable identity that imports and saved links use.
            self.fields["code"].disabled = True

    def clean_closes_at(self):
        opens = self.cleaned_data.get("opens_at")
        closes = self.cleaned_data.get("closes_at")
        if opens and closes and closes <= opens:
            raise forms.ValidationError("A room must close after it opens.")
        return closes


class VehicleForm(StyledFormMixin, FacilityChoiceMixin, forms.ModelForm):
    layout = [
        ["code", "name"],
        ["registration_number", "vehicle_class"],
        ["make", "model"],
        ["year", "seats"],
        ["transmission", "fuel_type"],
        ["road_tax_expiry", "status"],
    ]

    applies_to = Facility.AppliesTo.VEHICLE

    class Meta:
        model = Vehicle
        fields = (
            "code", "name", "registration_number", "make", "model", "year",
            "seats", "transmission", "fuel_type", "road_tax_expiry",
            "description", "facilities", "status",
        )
        widgets = {
            "road_tax_expiry": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "road_tax_expiry": (
                "Kept for the office. An untaxed car is withdrawn from the booking screens "
                "automatically, and requesters are not shown the reason."
            ),
            "status": (
                "Setting a car to maintenance hides it from the booking screens. Bookings "
                "already made are not cancelled — handle each deliberately, with a reason."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit_facilities()
        if self.instance.pk:
            self.fields["code"].disabled = True


class FacilityForm(StyledFormMixin, forms.ModelForm):
    """Display order is absent deliberately: it is set by dragging rows, not
    typed. A number field here would let two facilities claim the same position
    and would need the rest of the list renumbered by hand to insert anything."""
    layout = [["name", "code"], ["applies_to", "is_active"]]


    class Meta:
        model = Facility
        fields = ("name", "code", "applies_to", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["code"].disabled = True
            self.fields["code"].help_text = (
                "The code is fixed. Renaming the facility does not change it, so imports and "
                "saved links keep working."
            )
        else:
            self.fields["code"].required = False
            self.fields["code"].help_text = "Generated from the name. Once saved it never changes."

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("code"):
            name = cleaned.get("name") or ""
            code = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]
            if not code:
                self.add_error("name", "Give the facility a name.")
            elif Facility.objects.filter(code=code).exists():
                self.add_error(
                    "name", f'A facility with the code "{code}" already exists. Codes are unique.'
                )
            else:
                cleaned["code"] = code
                self.instance.code = code
        return cleaned

    def save(self, commit: bool = True) -> Facility:
        facility = super().save(commit=False)
        if not facility.pk:
            # A new facility goes to the end. Its position is then changed by
            # dragging, like every other facility's.
            last = Facility.objects.order_by("-display_order").first()
            facility.display_order = (last.display_order if last else 0) + 1
        if commit:
            facility.save()
            self.save_m2m()
        return facility


class ResourceImageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ResourceImage
        fields = ("image", "caption")

    def clean_image(self):
        upload = self.cleaned_data["image"]
        validate_image_upload(upload)
        return upload


class ResourceSearchForm(StyledFormMixin, forms.Form):
    """Filters for the browse and management lists. Applied in the query."""

    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(
        required=False, choices=[("", "All")] + list(ResourceStatus.choices)
    )
    facility = forms.ModelChoiceField(
        required=False, queryset=Facility.objects.filter(is_active=True), empty_label="Any facility"
    )
