"""Forms for key issue and return, at the Key Register and at the office kiosk."""

from __future__ import annotations

from django import forms

from apps.resources.validators import validate_image_upload
from config.forms import ImageInput, StyledFormMixin

MILEAGE_HELP = "The odometer reading in km, if you have it. You can leave this blank."


class IssueKeyForm(StyledFormMixin, forms.Form):
    """Who is collecting, when that is somebody else.

    The name is optional and the record is never left empty: blank means the
    person who booked came for the key, and the service writes their name.
    Typing it out again for the common case was work for nothing.
    """
    layout = [["collected_by_name", "collected_by_contact"], ["mileage_out"]]

    collected_by_name = forms.CharField(
        max_length=150,
        required=False,
        label="Collected by",
        help_text="Leave blank if the person who booked is collecting it themselves.",
    )
    collected_by_contact = forms.CharField(
        max_length=20, required=False, label="Telephone number"
    )
    mileage_out = forms.IntegerField(
        min_value=0, required=False, label="Mileage when collected", help_text=MILEAGE_HELP
    )

    def __init__(self, *args, vehicle: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not vehicle:
            del self.fields["mileage_out"]
            self.layout = [["collected_by_name", "collected_by_contact"]]


class ReturnKeyForm(StyledFormMixin, forms.Form):
    layout = [["returned_by_name"], ["mileage_in"], ["fuel_receipt"], ["condition_notes"]]

    returned_by_name = forms.CharField(
        max_length=150,
        label="Returned by",
        help_text="The person handing the key back.",
    )
    mileage_in = forms.IntegerField(
        min_value=0, required=False, label="Mileage when returned", help_text=MILEAGE_HELP
    )
    fuel_receipt = forms.ImageField(
        required=False,
        label="Petrol receipt",
        widget=ImageInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        help_text="A photo of the receipt, if petrol was bought. JPEG, PNG or WebP, up to 5 MB.",
    )
    condition_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Notes on condition",
        help_text="Anything the office should know, such as damage or something left behind.",
    )

    def __init__(self, *args, vehicle: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if not vehicle:
            del self.fields["mileage_in"]
            del self.fields["fuel_receipt"]
            self.layout = [["returned_by_name"], ["condition_notes"]]

    def clean_fuel_receipt(self):
        upload = self.cleaned_data.get("fuel_receipt")
        if upload:
            validate_image_upload(upload)
        return upload


class KioskLookupForm(StyledFormMixin, forms.Form):
    reference = forms.CharField(
        max_length=20,
        label="Booking number",
        help_text="The last four digits are enough for a booking today. The full number is "
        "in your confirmation email.",
        widget=forms.TextInput(
            attrs={"autocomplete": "off", "autofocus": True, "inputmode": "numeric"}
        ),
    )


class KioskExitForm(StyledFormMixin, forms.Form):
    password = forms.CharField(
        label="Admin password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
