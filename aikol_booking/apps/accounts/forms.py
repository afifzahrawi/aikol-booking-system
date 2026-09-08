"""Registration and account forms.

Every rule here is enforced again in the view or the model. A form is a
convenience for the person filling it in, never the place a rule lives alone.
"""

from __future__ import annotations

from django import forms

from config.forms import StyledFormMixin
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Affiliation, User


class RegistrationForm(StyledFormMixin, UserCreationForm):
    """Self-registration.

    Open to the public as well as to IIUM. The matriculation or staff number is
    asked for by default and withdrawn by a tick box, because the overwhelming
    majority of registrants are students and staff — making the common case the
    default is what keeps the form short for them.
    """

    not_iium = forms.BooleanField(
        required=False,
        label="I am not an IIUM student, lecturer or member of staff",
        help_text="Tick this and the matriculation or staff number is not required.",
    )

    class Meta:
        model = User
        fields = ("full_name", "email", "identification_number", "phone", "affiliation")
        labels = {"identification_number": "Matriculation or staff number"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identification_number"].required = False
        # Public is reachable only through the tick box, so it is not offered
        # as a choice that contradicts it.
        self.fields["affiliation"].choices = [
            (v, l) for v, l in Affiliation.choices if v != Affiliation.PUBLIC
        ]

    def clean_email(self) -> str:
        """Normalise only.

        Whether an account already exists is deliberately NOT reported here. A
        form that says "an account already exists for that address" is an
        address oracle: anybody can submit a list and learn which of their
        colleagues has registered. The view handles the collision instead — it
        shows the same confirmation page either way and emails the existing
        account to say somebody tried.
        """
        return self.cleaned_data["email"].strip().lower()

    def validate_unique(self) -> None:
        """Skip the model's uniqueness check on `email`, and only on `email`.

        This is the subtle half of not enumerating addresses. Suppressing the
        message in `clean_email` was not enough: `ModelForm._post_clean` runs
        `instance.validate_unique()` afterwards and adds "User with this Email
        address already exists." by itself. The form then fails, the view's
        `form_valid` never runs, and the oracle is intact — which is exactly
        what the test caught.

        Nothing is weakened by this. The column is still `unique=True`, so the
        database refuses a duplicate regardless; the view checks for the
        collision explicitly and takes the quiet path.
        """
        exclude = self._get_validation_exclusions()
        exclude.add("email")
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as exc:
            self._update_errors(exc)

    @property
    def email_already_registered(self) -> bool:
        email = (self.cleaned_data or {}).get("email", "")
        return bool(email) and User.objects.filter(email__iexact=email).exists()

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").lower()
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        is_iium = domain in settings.IIUM_EMAIL_DOMAINS
        not_iium = cleaned.get("not_iium")
        number = (cleaned.get("identification_number") or "").strip()

        if not_iium:
            # A member of the public carries no number. The column is unique, so
            # it must be NULL rather than an empty string — a second empty
            # string would collide.
            cleaned["identification_number"] = None
            cleaned["affiliation"] = Affiliation.PUBLIC
            if is_iium:
                self.add_error(
                    "not_iium",
                    "That is an IIUM address. Untick this and give your "
                    "matriculation or staff number.",
                )
        else:
            if not is_iium:
                self.add_error(
                    "email",
                    "Use your IIUM address ("
                    + " or ".join("@" + d for d in settings.IIUM_EMAIL_DOMAINS)
                    + "), or tick the box below if you are not from IIUM.",
                )
            if not number:
                self.add_error(
                    "identification_number",
                    "Give your matriculation or staff number, or tick the box below.",
                )
            elif User.objects.filter(identification_number__iexact=number).exists():
                # This one IS reported. A matriculation number is not a contact
                # address and cannot be probed for a list of people the way an
                # email can; and a silent merge of two people onto one number
                # would corrupt the booking record, which is worse.
                self.add_error(
                    "identification_number", "That number is already registered."
                )
            else:
                cleaned["identification_number"] = number
        return cleaned

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.identification_number = self.cleaned_data.get("identification_number") or None
        user.affiliation = self.cleaned_data.get("affiliation") or Affiliation.PUBLIC
        # The account exists but can do nothing until the address is confirmed.
        user.email_verified = False
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(StyledFormMixin, AuthenticationForm):
    """Sign in with an email address; there is no username in this system."""

    username = forms.EmailField(label="Email address")

    def clean_username(self) -> str:
        return self.cleaned_data["username"].strip().lower()


class DrivingLicenceForm(StyledFormMixin, forms.ModelForm):
    """Captured on the first self-drive booking, not at registration — most
    people never need it, and it is personal data we would rather not hold
    without a reason."""

    class Meta:
        model = User
        fields = ("licence_number", "licence_expiry")
        widgets = {"licence_expiry": forms.DateInput(attrs={"type": "date"})}
