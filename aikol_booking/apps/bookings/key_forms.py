"""Forms for key issue and return."""

from __future__ import annotations

from django import forms

from config.forms import StyledFormMixin


class IssueKeyForm(StyledFormMixin, forms.Form):
    """Who is collecting is asked for, not assumed.

    Defaulting this to the person who booked would be a guess dressed up as a
    record, and the whole reason decision 17 exists is that the two are often
    different people.
    """
    layout = [["collected_by_name", "collected_by_contact"]]


    collected_by_name = forms.CharField(
        max_length=150,
        label="Collected by",
        help_text="The person actually taking the key. Often not the person who booked.",
    )
    collected_by_contact = forms.CharField(
        max_length=20, required=False, label="Their telephone number"
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
        help_text="Anything the office should know — damage, something left behind.",
    )
