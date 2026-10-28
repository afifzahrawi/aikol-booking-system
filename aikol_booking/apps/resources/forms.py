"""Forms for resource management."""

from __future__ import annotations

import re

from django import forms
from django.db.models import Q

from config.forms import StyledFormMixin, yes_no_field

from .models import (
    Building,
    Facility,
    ResourceImage,
    ResourceStatus,
    Vehicle,
    Venue,
    VenueType,
)
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
        ["building", "location"],
        ["venue_type", "floor"],
        ["capacity"],
        ["opens_at", "closes_at"],
    ]

    applies_to = Facility.AppliesTo.VENUE

    class Meta:
        model = Venue
        fields = (
            "code", "name", "venue_type", "building", "location", "floor", "capacity",
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
        # Only offered types, plus the venue's own if it has since been
        # withdrawn, so editing an old room never blanks its type.
        offered = Q(is_active=True)
        if self.instance.pk and self.instance.venue_type_id:
            offered |= Q(code=self.instance.venue_type_id)
        self.fields["venue_type"].queryset = VenueType.objects.filter(offered)
        self.fields["venue_type"].empty_label = "Choose a type"
        # The same rule for buildings: hidden ones are not offered to new rooms.
        shown = Q(is_active=True)
        if self.instance.pk and self.instance.building_id:
            shown |= Q(pk=self.instance.building_id)
        self.fields["building"].queryset = Building.objects.filter(shown)
        self.fields["building"].empty_label = "Choose a building"
        self.fields["building"].required = True
        self.fields["building"].help_text = "Add buildings under Resources, Buildings."
        self.fields["location"].label = "Where in the building"
        self.fields["location"].help_text = "For example Level 3, east wing."
        if self.instance.pk:
            # The code is the stable identity that imports and saved links use.
            self.fields["code"].disabled = True

    def clean_closes_at(self):
        opens = self.cleaned_data.get("opens_at")
        closes = self.cleaned_data.get("closes_at")
        if opens and closes and closes <= opens:
            raise forms.ValidationError("A venue must close after it opens.")
        return closes

    def save(self, commit: bool = True) -> Venue:
        venue = super().save(commit=False)
        if not venue.pk:
            # New venues join the bottom of the list. Their position can then
            # be changed with the reorder controls, rather than by maintaining
            # a fragile number field by hand.
            last = Venue.objects.order_by("-display_order", "-pk").first()
            venue.display_order = (last.display_order if last else 0) + 1
        if commit:
            venue.save()
            self.save_m2m()
        return venue


class VehicleForm(StyledFormMixin, forms.ModelForm):
    layout = [
        ["code", "name"],
        ["registration_number", "vehicle_class"],
        ["make", "model"],
        ["year", "seats"],
        ["transmission", "fuel_type"],
        ["road_tax_expiry", "status"],
    ]

    class Meta:
        model = Vehicle
        fields = (
            "code", "name", "registration_number", "make", "model", "year",
            "seats", "transmission", "fuel_type", "road_tax_expiry",
            "description", "status",
        )
        widgets = {
            "road_tax_expiry": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "road_tax_expiry": (
                "Kept for the office. An untaxed vehicle is withdrawn from the booking screens "
                "automatically, and requesters are not shown the reason."
            ),
            "status": (
                "Setting a vehicle to maintenance hides it from the booking screens. Bookings "
                "already made are not cancelled. Handle each one, with a reason."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["code"].disabled = True


class VenueTypeForm(StyledFormMixin, forms.ModelForm):
    """The kinds of room a venue can be. The code, like a facility's, is fixed
    once saved so imports and saved filter links keep working."""

    is_active = yes_no_field(
        "Offered", help_text="Choose No to stop offering it. Venues that already have it keep it."
    )
    layout = [["name", "code"], ["is_active"]]

    class Meta:
        model = VenueType
        fields = ("name", "code", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["code"].disabled = True
            self.fields["code"].help_text = (
                "The code is fixed. Renaming the type does not change it."
            )
        else:
            self.fields["code"].required = False
            self.fields["code"].help_text = "Generated from the name. Once saved it never changes."

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("code"):
            name = cleaned.get("name") or ""
            code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:20]
            if not code:
                self.add_error("name", "Give the type a name.")
            elif VenueType.objects.filter(code=code).exists():
                self.add_error("name", "A venue type with this name already exists.")
            else:
                cleaned["code"] = code
                self.instance.code = code
        return cleaned


class BuildingForm(StyledFormMixin, forms.ModelForm):
    """A building venues are in. Renaming it renames it everywhere at once."""

    is_active = yes_no_field(
        "Shown", help_text="Choose No to hide it from new venues. Rooms already in it keep it."
    )
    layout = [["name"], ["is_active", "display_order"]]

    class Meta:
        model = Building
        fields = ("name", "is_active", "display_order")
        labels = {"display_order": "Position in lists"}
        help_texts = {"display_order": "Lower numbers come first on the venue page."}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        clash = Building.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A building with this name already exists.")
        return name


class FacilityForm(StyledFormMixin, forms.ModelForm):
    """Display order is absent deliberately: it is set by dragging rows, not
    typed. A number field here would let two facilities claim the same position
    and would need the rest of the list renumbered by hand to insert anything."""
    is_active = yes_no_field("Offered", help_text="Choose No to stop offering it. Venues that already have it keep it.")
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


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Django's file field takes one upload; its widget can offer several.

    Without this the field receives a list and rejects it as "required",
    because FileField.clean expects a single file object.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        one = super().clean
        if isinstance(data, (list, tuple)):
            return [one(item, initial) for item in data]
        return [one(data, initial)]


class ResourceImageForm(StyledFormMixin, forms.Form):
    """One or several photographs at a time.

    Django's own file field takes a single upload, so the list is read from
    the raw files and each one validated separately: an administrator with a
    folder of photographs should not have to add them one at a time, and one
    bad file should say which it was rather than failing the batch silently.
    """

    images = MultipleFileField(
        label="Photographs",
        widget=MultipleFileInput(attrs={"multiple": True, "accept": "image/jpeg,image/png,image/webp"}),
        help_text="JPEG, PNG or WebP, up to 5 MB each. Choose several, or drop them on the page.",
    )
    caption = forms.CharField(
        max_length=120,
        required=False,
        help_text="Used for all of the photographs in this upload.",
    )

    def clean_images(self):
        uploads = [upload for upload in self.cleaned_data["images"] if upload]
        if not uploads:
            raise forms.ValidationError("Choose at least one photograph.")
        for upload in uploads:
            try:
                validate_image_upload(upload)
            except forms.ValidationError as exc:
                raise forms.ValidationError(f"{upload.name}: {' '.join(exc.messages)}") from exc
        return uploads


class ResourceSearchForm(StyledFormMixin, forms.Form):
    """Filters for the browse and management lists. Applied in the query."""

    q = forms.CharField(required=False, label="Search")
    status = forms.ChoiceField(
        required=False, choices=[("", "All")] + list(ResourceStatus.choices)
    )
    facility = forms.ModelChoiceField(
        required=False, queryset=Facility.objects.filter(is_active=True), empty_label="Any facility"
    )
