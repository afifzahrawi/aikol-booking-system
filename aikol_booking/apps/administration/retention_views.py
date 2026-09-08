"""The retention screen. Nothing here runs on a schedule."""

from __future__ import annotations

from django.contrib import messages as flash
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render

from . import retention
from .models import SystemSetting


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


@administrator_required
def retention_screen(request):
    if request.method == "POST":
        try:
            summary = retention.run_cleanup(
                actor=request.user,
                confirmation=request.POST.get("confirmation", ""),
                action=request.POST.get("action") or None,
            )
        except ValidationError as exc:
            for problem in exc.messages:
                flash.error(request, problem)
        else:
            if summary["removed"]:
                flash.success(
                    request,
                    f"{summary['removed']} records {summary['action'].lower()}ed and removed."
                    + (f" File: {summary['path']}" if summary["path"] else ""),
                )
            else:
                flash.info(request, "No record is old enough to be eligible.")
            return redirect("administration:retention")

    return render(
        request,
        "administration/retention.html",
        {
            "preview": retention.preview(),
            "years": SystemSetting.get_int("booking_retention_years"),
            "phrase": retention.TYPED_CONFIRMATION,
            "export_dir": retention.EXPORT_DIR,
        },
    )
