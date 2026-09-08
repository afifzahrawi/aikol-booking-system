"""Administrator forms: booking on behalf, user management, site content."""

from __future__ import annotations

from django import forms

from config.forms import StyledFormMixin

from apps.accounts.models import Affiliation, Role, User

from .models import SiteContent, SystemSetting


class OnBehalfForm(StyledFormMixin, forms.Form):
    """Decision 14: an administrator may create a booking for somebody else.

    The person is searched for, not scrolled to. A Kulliyyah has thousands of
    students and a `<select>` of all of them is unusable by the time it matters.
    """

    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("full_name"),
        label="Booking for",
        help_text="Search by name, email or matriculation number.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].widget.attrs["list"] = "user-options"


class UserAdminForm(StyledFormMixin, forms.ModelForm):
    """Roles and activation. A password is never set here — an administrator
    who can read or choose someone else's password is a liability, and the
    reset flow already exists."""

    class Meta:
        model = User
        fields = (
            "full_name", "email", "identification_number", "phone",
            "affiliation", "role", "is_active", "email_verified",
        )
        help_texts = {
            "role": "What they may do in the system.",
            "affiliation": "What they are. Lecturers and staff may drive a Kulliyyah car.",
            "is_active": "Deactivating retires an account. It never deletes it, and history stays.",
            "email_verified": "Tick only to confirm an address by hand when email has failed.",
        }


class SystemSettingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = ("value",)


class SiteContentForm(StyledFormMixin, forms.ModelForm):
    """Header and footer wording — content, not code."""

    class Meta:
        model = SiteContent
        fields = (
            "site_name", "subtitle", "organisation", "logo", "logo_alt",
            "address", "contact_heading", "phone", "email", "office_hours",
        )
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        # A changed file is an UploadedFile; an unchanged one is the stored
        # FieldFile and must not be re-validated as though it were an upload.
        if logo and hasattr(logo, "content_type"):
            from apps.resources.validators import validate_image_upload

            validate_image_upload(logo)
        return logo
