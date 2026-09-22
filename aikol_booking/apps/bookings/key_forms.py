"""Forms for key issue and return."""

from __future__ import annotations

from django import forms

from config.forms import StyledFormMixin


class IssueKeyForm(StyledFormMixin, forms.Form):
    """Who is collecting, when that is somebody else.

    The name is optional and the record is never left empty: blank means the
    person who booked came for the key, and the service writes their name.
    Typing it out again for the common case was work for nothing.
    """
    layout = [["collected_by_name", "collected_by_contact"]]

    collected_by_name = forms.CharField(
        max_length=150,
        required=False,
        label="Collected by",
        help_text="Leave blank if the person who booked is collecting it themselves.",
    )
    collected_by_contact = forms.CharField(
        max_length=20, required=False, label="Telephone number"
    )


class ReturnKeyForm(StyledFormMixin, forms.Form):
    returned_by_name = forms.CharField(
        max_length=150,
        label="Returned by",
        help_text="The person handing the key back.",
    )
    condition_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Notes on condition",
        help_text="Anything the office should know, such as damage or something left behind.",
    )
