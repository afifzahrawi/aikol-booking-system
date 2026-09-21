"""Administrator forms: booking on behalf, user management, site content."""

from __future__ import annotations

from django import forms

from config.forms import StyledFormMixin

from apps.accounts.models import Affiliation, Role, User
from apps.notifications.models import EmailConfiguration

from .models import Announcement, SiteContent, SystemSetting


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
    layout = [
        ["full_name", "email"],
        ["identification_number", "phone"],
        ["affiliation", "role"],
        ["is_active", "email_verified"],
    ]


    class Meta:
        model = User
        fields = (
            "full_name", "email", "identification_number", "phone",
            "affiliation", "role", "is_active", "email_verified",
        )
        labels = {"is_active": "Active account", "email_verified": "Email address verified"}
        help_texts = {
            "role": "What they may do in the system.",
            "affiliation": "Student, staff or public.",
            "is_active": "Untick to retire the account. Its booking history is kept.",
            "email_verified": "Tick only to confirm the address yourself when the verification email cannot reach them.",
        }


class SystemSettingForm(StyledFormMixin, forms.ModelForm):
    """One value at a time. The screen offers a choice where the setting has
    one; this form refuses anything outside it, whatever the browser sent."""

    class Meta:
        model = SystemSetting
        fields = ("value",)

    def clean_value(self):
        value = self.cleaned_data["value"].strip()
        setting = self.instance
        allowed = [choice for choice, _ in setting.choices]
        if allowed and value not in allowed:
            raise forms.ValidationError("Choose one of the offered values.")
        if setting.input_kind == "number":
            if not value.isdigit() or int(value) < 1:
                raise forms.ValidationError("Enter a whole number of 1 or more.")
        if setting.input_kind == "time":
            import datetime as dt

            try:
                dt.time.fromisoformat(value)
            except ValueError as exc:
                raise forms.ValidationError("Enter a time as HH:MM.") from exc
        return value


class EmailConfigurationForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the stored password.",
    )
    layout = [
        ["host", "port"],
        ["username", "password"],
        ["use_tls", "use_ssl"],
        ["default_from_email", "timeout_seconds"],
    ]

    class Meta:
        model = EmailConfiguration
        fields = (
            "host",
            "port",
            "username",
            "password",
            "use_tls",
            "use_ssl",
            "default_from_email",
            "timeout_seconds",
            "is_active",
        )
        labels = {
            "host": "SMTP host",
            "port": "SMTP port",
            "username": "SMTP username",
            "use_tls": "Use TLS",
            "use_ssl": "Use SSL",
            "default_from_email": "From address",
            "timeout_seconds": "Connection timeout (seconds)",
            "is_active": "Enable email delivery",
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("use_tls") and cleaned.get("use_ssl"):
            raise forms.ValidationError("Choose TLS or SSL, not both.")
        if cleaned.get("is_active") and not cleaned.get("host"):
            self.add_error("host", "Enter an SMTP host before enabling email delivery.")
        return cleaned

    def save(self, commit=True):
        configuration = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            configuration.set_password(password)
        if commit:
            configuration.save()
        return configuration


class SiteContentForm(StyledFormMixin, forms.ModelForm):
    """Header and footer wording — content, not code."""
    layout = [
        ["site_name", "subtitle"],
        ["organisation", "logo_alt"],
        ["logo", "iium_logo"],
        ["login_image", "home_image"],
        ["login_intro_heading", "login_intro"],
        ["contact_heading", "office_hours"],
        ["phone", "email"],
    ]


    class Meta:
        model = SiteContent
        fields = (
            "site_name", "subtitle", "organisation", "logo", "logo_alt",
            "iium_logo", "iium_logo_alt", "login_image", "home_image",
            "login_intro_heading", "login_intro", "login_points", "address",
            "contact_heading", "phone", "email", "office_hours",
        )
        widgets = {
            "login_intro": forms.Textarea(attrs={"rows": 4}),
            "login_points": forms.Textarea(attrs={"rows": 4}),
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def _clean_image(self, field_name):
        image = self.cleaned_data.get(field_name)
        # A changed file is an UploadedFile; an unchanged one is the stored
        # FieldFile and must not be re-validated as though it were an upload.
        if image and hasattr(image, "content_type"):
            from apps.resources.validators import validate_image_upload

            validate_image_upload(image)
        return image

    def clean_logo(self):
        return self._clean_image("logo")

    def clean_iium_logo(self):
        return self._clean_image("iium_logo")

    def clean_login_image(self):
        return self._clean_image("login_image")

    def clean_home_image(self):
        return self._clean_image("home_image")


class AnnouncementForm(StyledFormMixin, forms.ModelForm):
    layout = [["tone", "is_active"], ["starts_at", "ends_at"]]

    class Meta:
        model = Announcement
        fields = ("title", "message", "tone", "is_active", "starts_at", "ends_at")
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
            "starts_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "ends_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ("%Y-%m-%dT%H:%M",)

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        ends_at = cleaned.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "The end must be after the start.")
        return cleaned
