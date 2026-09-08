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


def associate_help_text(form: forms.BaseForm) -> None:
    """Point each control at its own help text with `aria-describedby`.

    Without this a screen-reader user hears the label and nothing else: "The
    room seats 30" and "Kept for the office" are read by sighted users and
    silently skipped by everyone else. The id must match what the template
    renders, so the two are kept together deliberately — see `_field.html`.
    """
    for name, field in form.fields.items():
        if not field.help_text:
            continue
        described = f"help_{form.add_prefix(name)}"
        existing = field.widget.attrs.get("aria-describedby", "")
        field.widget.attrs["aria-describedby"] = (
            f"{existing} {described}".strip() if existing else described
        )


class StyledFormMixin:
    """Mix in before `forms.Form` / `forms.ModelForm`.

    Set `layout` to group fields into rows. A booking's date and time belong
    beside each other, not stacked in a column of eleven single fields:

        layout = [["start_date", "start_time"], ["end_date", "end_time"]]

    Any field not named in `layout` renders full width, in its declared order,
    after the grouped ones. Naming a field that does not exist is ignored rather
    than raised, because a form that removes a field conditionally — as the
    booking form does for venues versus vehicles — would otherwise break.
    """

    layout: list[list[str]] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_widgets(self)
        associate_help_text(self)

    def rows(self):
        """Yield (is_row, fields) so a template renders groups without knowing
        the field names."""
        grouped = []
        used = set()
        for group in self.layout:
            fields = [self[name] for name in group if name in self.fields]
            if len(fields) > 1:
                grouped.append((True, fields))
                used.update(f.name for f in fields)
            elif fields:
                grouped.append((False, fields))
                used.add(fields[0].name)
        for name in self.fields:
            if name not in used:
                grouped.append((False, [self[name]]))
        return grouped
