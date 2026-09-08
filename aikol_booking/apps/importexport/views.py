"""Bulk import and export screens. Administrator-only."""

from __future__ import annotations

import csv

from django import forms

from config.forms import StyledFormMixin
from django.contrib import messages as flash
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render

from apps.audit.services import log_action
from apps.bookings.models import Booking, BookingStatus
from apps.resources.models import ResourceType

from . import exports
from .services import TEMPLATES, apply_plan, validate


def administrator_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Sign in first.")
        if not request.user.is_administrator:
            raise PermissionDenied("Administrators only.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


class UploadForm(StyledFormMixin, forms.Form):
    kind = forms.ChoiceField(choices=[(k, k.title()) for k in TEMPLATES])
    csv_file = forms.FileField(label="CSV file")


@administrator_required
def data_management(request):
    """Upload, validate, preview. Nothing is written on this request."""
    form = UploadForm(request.POST or None, request.FILES or None)
    plan = None
    if request.method == "POST" and form.is_valid():
        plan = validate(form.cleaned_data["kind"], form.cleaned_data["csv_file"])
        # The validated plan is held in the session so the confirm step imports
        # exactly what was previewed, rather than re-reading a file that could
        # have changed underneath it.
        request.session["import_kind"] = plan.kind
        request.session["import_rows"] = [
            {"line": r.line, "data": {k: str(v) for k, v in r.data.items()}}
            for r in plan.valid
        ]
    return render(
        request,
        "importexport/data_management.html",
        {"form": form, "plan": plan, "kinds": list(TEMPLATES)},
    )


@administrator_required
def confirm_import(request):
    if request.method != "POST":
        return redirect("importexport:data_management")

    kind = request.session.get("import_kind")
    stored = request.session.get("import_rows") or []
    if not kind or not stored:
        flash.error(request, "There is nothing waiting to be imported. Upload a file first.")
        return redirect("importexport:data_management")

    # Rebuild the plan from what was previewed, then re-validate it: the
    # database may have changed since the preview, and importing rows that are
    # no longer valid would defeat the checks entirely.
    from .services import ImportPlan, RowResult

    plan = ImportPlan(kind=kind)
    seen = {}
    validator = {
        "facilities": "_validate_facility",
        "users": "_validate_user",
        "venues": "_validate_venue",
        "vehicles": "_validate_vehicle",
    }[kind]
    from . import services as service_module

    check = getattr(service_module, validator)
    for entry in stored:
        result = RowResult(line=entry["line"], data=dict(entry["data"]))
        check(result, seen)
        plan.rows.append(result)

    if not plan.valid:
        flash.error(
            request,
            "None of those rows is still valid — the database has changed since the preview. "
            "Upload the file again to see why.",
        )
        return redirect("importexport:data_management")

    summary = apply_plan(plan)
    log_action(
        actor=request.user,
        action="BULK_IMPORT",
        entity_type=kind.title(),
        description=(
            f"{summary['created']} created, {summary['updated']} updated, "
            f"{summary['skipped']} skipped."
        ),
        request=request,
    )
    request.session.pop("import_kind", None)
    request.session.pop("import_rows", None)
    flash.success(
        request,
        f"{summary['created']} {kind} created"
        + (f", {summary['updated']} updated" if summary["updated"] else "")
        + ".",
    )
    return redirect("importexport:data_management")


@administrator_required
def template_csv(request, kind: str):
    """The blank template, so an officer starts from the right columns."""
    if kind not in TEMPLATES:
        raise PermissionDenied("Unknown template.")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="aikol-{kind}-template.csv"'
    csv.writer(response).writerow(TEMPLATES[kind])
    return response


def _log_export(request, what: str) -> None:
    log_action(
        actor=request.user,
        action="DATA_EXPORTED",
        entity_type=what.title(),
        description=f"{what} exported to CSV.",
        request=request,
    )


@administrator_required
def export_users(request):
    _log_export(request, "users")
    return exports.export_users()


@administrator_required
def export_venues(request):
    _log_export(request, "venues")
    return exports.export_venues()


@administrator_required
def export_vehicles(request):
    _log_export(request, "vehicles")
    return exports.export_vehicles()


@administrator_required
def export_facilities(request):
    _log_export(request, "facilities")
    return exports.export_facilities()


def export_bookings(request):
    """Limited to what the requester is authorised to see.

    An approver may export the bookings they can decide; an ordinary user gets
    403 rather than a filtered file, because a booking export is not something
    an ordinary account has any business generating.
    """
    if not request.user.is_authenticated or not request.user.is_approver:
        raise PermissionDenied("Only an approver or administrator may export bookings.")

    bookings = Booking.objects.all()
    status = request.GET.get("status")
    if status in BookingStatus.values:
        bookings = bookings.filter(status=status)
    kind = request.GET.get("kind")
    if kind in ResourceType.values:
        bookings = bookings.filter(resource__resource_type=kind)
    since = request.GET.get("from")
    until = request.GET.get("to")
    if since:
        bookings = bookings.filter(start_at__date__gte=since)
    if until:
        bookings = bookings.filter(start_at__date__lte=until)

    _log_export(request, "bookings")
    return exports.export_bookings(bookings)
