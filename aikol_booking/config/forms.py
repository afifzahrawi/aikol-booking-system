"""Widget styling, applied once.

The stylesheet ported from the prototype styles form controls by CLASS —
`.input`, `.select`, `.textarea` — but Django renders a bare `<input>` with no
class of its own. Every form in the application was therefore unstyled: the
1,084-line stylesheet was loading and doing nothing for any control on any page.

This lives in `config/` rather than in an app because every app's forms need it,
and the architecture rule says apps may import from `accounts`, `resources`,
`notifications` and `audit` only. Form-control plumbing belongs to none of those.
"""

from __future__ import annotations

from django import forms

TEXT_WIDGETS = (
    forms.TextInput,
    forms.EmailInput,
    forms.NumberInput,
    forms.PasswordInput,
    forms.URLInput,
    forms.DateInput,
    forms.TimeInput,
    forms.DateTimeInput,
    forms.FileInput,
    forms.ClearableFileInput,
)


def style_widgets(form: forms.BaseForm) -> None:
    """Give every control the class the stylesheet is looking for.

    Checkboxes, radios and file inputs are left alone: they are styled by the
    surrounding `.checkline` markup, and forcing `.input` on them would give a
    checkbox a 300px-wide text-field border.
    """
    for field in form.fields.values():
        widget = field.widget
        existing = widget.attrs.get("class", "")
        if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple,
                               forms.RadioSelect)):
            continue
        if isinstance(widget, forms.Textarea):
            css = "textarea"
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            css = "select"
        elif isinstance(widget, TEXT_WIDGETS):
            css = "input"
        else:
            continue
        widget.attrs["class"] = f"{existing} {css}".strip()

        # A required field says so to assistive technology as well as visually.
        if field.required:
            widget.attrs.setdefault("aria-required", "true")


class StyledFormMixin:
    """Mix in before `forms.Form` / `forms.ModelForm`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_widgets(self)
