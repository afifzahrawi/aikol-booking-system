"""Key custody screens. Administrator-only: the keys are held in the office."""

from __future__ import annotations

from django.contrib import messages as flash
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.services import log_action

from .key_forms import IssueKeyForm, ReturnKeyForm
from .keys import issue_key, keys_awaiting_collection, outstanding_keys, return_key
from .models import Booking, KeyHandover


def administrator_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Sign in first.")
        if not request.user.is_administrator:
            raise PermissionDenied("Keys are held by the Kulliyyah office.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


@administrator_required
def key_register(request):
    """Everything about keys on one screen: out, overdue, and still to collect."""
    out = list(outstanding_keys())
    now = timezone.now()
    overdue = [h for h in out if h.booking.end_at < now]
    return render(
        request,
        "bookings/keys.html",
        {
            "outstanding": out,
            "overdue": overdue,
            "awaiting": keys_awaiting_collection()[:50],
            "now": now,
        },
    )


@administrator_required
def key_issue(request, pk: int):
    booking = get_object_or_404(Booking.objects.select_related("resource", "user"), pk=pk)
    form = IssueKeyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            issue_key(
                booking,
                issued_by=request.user,
                collected_by_name=form.cleaned_data["collected_by_name"],
                collected_by_contact=form.cleaned_data["collected_by_contact"],
            )
        except ValidationError as exc:
            for problem in exc.messages:
                form.add_error(None, problem)
        else:
            log_action(
                actor=request.user,
                action="KEY_ISSUED",
                entity_type="Booking",
                entity_id=booking.pk,
                # The collector's telephone number is personal data and stays
                # out of the log's free text.
                description=f"Key for {booking.booking_reference} issued to "
                f"{form.cleaned_data['collected_by_name']}.",
                request=request,
            )
            flash.success(request, f"Key issued for {booking.booking_reference}.")
            return redirect("bookings:keys")
    return render(
        request,
        "bookings/key_issue.html",
        {"booking": booking, "form": form, "action": "issue"},
    )


@administrator_required
def key_return(request, pk: int):
    booking = get_object_or_404(Booking.objects.select_related("resource", "user"), pk=pk)
    handover = KeyHandover.objects.filter(booking=booking).first()
    form = ReturnKeyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            return_key(
                booking,
                returned_to=request.user,
                returned_by_name=form.cleaned_data["returned_by_name"],
                condition_notes=form.cleaned_data["condition_notes"],
            )
        except ValidationError as exc:
            for problem in exc.messages:
                form.add_error(None, problem)
        else:
            log_action(
                actor=request.user,
                action="KEY_RETURNED",
                entity_type="Booking",
                entity_id=booking.pk,
                description=f"Key for {booking.booking_reference} returned by "
                f"{form.cleaned_data['returned_by_name']}.",
                request=request,
            )
            flash.success(request, f"Key returned for {booking.booking_reference}.")
            return redirect("bookings:keys")
    return render(
        request,
        "bookings/key_issue.html",
        {"booking": booking, "form": form, "action": "return", "handover": handover},
    )
