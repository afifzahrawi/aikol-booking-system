"""Key custody screens. Administrator-only: the keys are held in the office.

Two ways in. The Key Register is the Admin's own workspace. The kiosk is a
locked, single-purpose view of the same records for the office PC, where people
record their own collection or return. It is opened from an Admin's session and
that session then reaches nothing but the kiosk until the Admin's password is
entered again (see `config.middleware.KioskLockMiddleware`).
"""

from __future__ import annotations

from django.contrib import messages as flash
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.throttle import is_throttled
from apps.audit.services import log_action
from apps.resources.models import ResourceType

from .key_forms import IssueKeyForm, KioskExitForm, KioskLookupForm, ReturnKeyForm
from .keys import (
    awaiting_confirmation,
    confirm_key_entry,
    find_by_reference,
    find_for_kiosk,
    kiosk_today,
    issue_key,
    keys_awaiting_collection,
    outstanding_keys,
    reject_key_entry,
    return_key,
)
from .models import Booking, KeyHandover, Via

PAGE_SIZE = 20
KIOSK_SESSION_KEY = "kiosk_mode"
KINDS = {"venue": ResourceType.VENUE, "vehicle": ResourceType.VEHICLE}


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


def _of_kind(queryset, kind: str, via_booking: bool):
    field = "booking__resource__resource_type" if via_booking else "resource__resource_type"
    return queryset.filter(**{field: KINDS[kind]})


def _search(queryset, term: str, via_booking: bool):
    if not term:
        return queryset
    prefix = "booking__" if via_booking else ""
    return queryset.filter(
        Q(**{f"{prefix}booking_reference__icontains": term})
        | Q(**{f"{prefix}user__full_name__icontains": term})
    )


@administrator_required
def key_register(request):
    """Venue keys and vehicle keys kept apart, one paginated queue at a time."""
    now = timezone.now()
    kind = request.GET.get("kind", "venue")
    if kind not in KINDS:
        kind = "venue"
    term = (request.GET.get("q") or "").strip()
    tab = request.GET.get("tab", "awaiting")
    if tab not in {"awaiting", "out", "confirm"}:
        tab = "awaiting"

    out = _of_kind(outstanding_keys(), kind, True)
    awaiting = _of_kind(keys_awaiting_collection(), kind, False)
    confirm = _of_kind(awaiting_confirmation(), kind, True)
    rows = {"awaiting": awaiting, "out": out, "confirm": confirm}[tab]
    rows = _search(rows, term, via_booking=tab != "awaiting")
    page = Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))

    # Waiting confirmations are counted for both kinds, so a kiosk entry for a
    # car is not missed while the Admin is looking at room keys.
    all_confirm = awaiting_confirmation()
    return render(
        request,
        "bookings/keys.html",
        {
            "page": page,
            "tab": tab,
            "kind": kind,
            "q": term,
            "outstanding_count": out.count(),
            "awaiting_count": awaiting.count(),
            "confirm_count": confirm.count(),
            "confirm_by_kind": {
                "venue": _of_kind(all_confirm, "venue", True).count(),
                "vehicle": _of_kind(all_confirm, "vehicle", True).count(),
            },
            "overdue_count": out.filter(booking__end_at__lt=now).count(),
            "querystring": f"kind={kind}&tab={tab}&q={term}&",
            "page_range": page.paginator.get_elided_page_range(
                page.number, on_each_side=2, on_ends=1
            ),
            "now": now,
        },
    )


def _log_issue(request, booking, handover, via: str) -> None:
    where = " at the office kiosk, awaiting confirmation" if via == Via.KIOSK else ""
    log_action(
        actor=request.user,
        action="KEY_ISSUED_KIOSK" if via == Via.KIOSK else "KEY_ISSUED",
        entity_type="Booking",
        entity_id=booking.pk,
        # The collector's telephone number is personal data and stays out of
        # the log's free text. Mileage is not personal and helps a dispute.
        description=f"Key for {booking.booking_reference} issued to "
        f"{handover.collected_by_name}{where}."
        + (f" Mileage out {handover.mileage_out} km." if handover.mileage_out is not None else ""),
        request=request,
    )


def _log_return(request, booking, handover, via: str) -> None:
    where = " at the office kiosk, awaiting confirmation" if via == Via.KIOSK else ""
    extra = ""
    if handover.mileage_in is not None:
        extra += f" Mileage in {handover.mileage_in} km."
    if handover.fuel_receipt:
        extra += " Petrol receipt attached."
    log_action(
        actor=request.user,
        action="KEY_RETURNED_KIOSK" if via == Via.KIOSK else "KEY_RETURNED",
        entity_type="Booking",
        entity_id=booking.pk,
        description=f"Key for {booking.booking_reference} returned by "
        f"{handover.returned_by_name}{where}.{extra}",
        request=request,
    )


def _do_issue(request, booking, form, via: str):
    try:
        handover = issue_key(
            booking,
            issued_by=request.user,
            collected_by_name=form.cleaned_data["collected_by_name"],
            collected_by_contact=form.cleaned_data["collected_by_contact"],
            mileage_out=form.cleaned_data.get("mileage_out"),
            via=via,
        )
    except ValidationError as exc:
        for problem in exc.messages:
            form.add_error(None, problem)
        return None
    _log_issue(request, booking, handover, via)
    return handover


def _do_return(request, booking, form, via: str):
    try:
        handover = return_key(
            booking,
            returned_to=request.user,
            returned_by_name=form.cleaned_data["returned_by_name"],
            condition_notes=form.cleaned_data["condition_notes"],
            mileage_in=form.cleaned_data.get("mileage_in"),
            fuel_receipt=form.cleaned_data.get("fuel_receipt"),
            via=via,
        )
    except ValidationError as exc:
        for problem in exc.messages:
            form.add_error(None, problem)
        return None
    _log_return(request, booking, handover, via)
    return handover


def _register_url(booking) -> str:
    kind = "vehicle" if booking.is_vehicle else "venue"
    return f"{reverse('bookings:keys')}?kind={kind}"


@administrator_required
def key_issue(request, pk: int):
    booking = get_object_or_404(Booking.objects.select_related("resource", "user"), pk=pk)
    form = IssueKeyForm(request.POST or None, vehicle=booking.is_vehicle)
    if request.method == "POST" and form.is_valid():
        if _do_issue(request, booking, form, Via.OFFICE):
            flash.success(request, f"Key issued for {booking.booking_reference}.")
            return redirect(_register_url(booking))
    return render(
        request,
        "bookings/key_issue.html",
        {"booking": booking, "form": form, "action": "issue"},
    )


@administrator_required
def key_return(request, pk: int):
    booking = get_object_or_404(Booking.objects.select_related("resource", "user"), pk=pk)
    handover = KeyHandover.objects.filter(booking=booking).first()
    form = ReturnKeyForm(request.POST or None, request.FILES or None, vehicle=booking.is_vehicle)
    if request.method == "POST" and form.is_valid():
        if _do_return(request, booking, form, Via.OFFICE):
            flash.success(request, f"Key returned for {booking.booking_reference}.")
            return redirect(_register_url(booking))
    return render(
        request,
        "bookings/key_issue.html",
        {"booking": booking, "form": form, "action": "return", "handover": handover},
    )


@administrator_required
@require_POST
def key_confirm(request, pk: int, step: str):
    """Confirm or reject a kiosk entry. `decision` is "confirm" or "reject"."""
    if step not in {"issue", "return"}:
        raise PermissionDenied("Unknown step.")
    handover = get_object_or_404(
        KeyHandover.objects.select_related("booking", "booking__resource"), pk=pk
    )
    booking = handover.booking
    noun = "collection" if step == "issue" else "return"
    reject = request.POST.get("decision") == "reject"
    try:
        if reject:
            reject_key_entry(handover, step)
        else:
            confirm_key_entry(handover, step, confirmed_by=request.user)
    except ValidationError as exc:
        flash.error(request, " ".join(exc.messages))
    else:
        log_action(
            actor=request.user,
            action=f"KEY_{'ISSUE' if step == 'issue' else 'RETURN'}_"
            f"{'REJECTED' if reject else 'CONFIRMED'}",
            entity_type="Booking",
            entity_id=booking.pk,
            description=f"Kiosk {noun} for {booking.booking_reference} "
            f"{'rejected and cleared' if reject else 'confirmed'}.",
            request=request,
        )
        flash.success(
            request,
            f"{noun.capitalize()} for {booking.booking_reference} "
            f"{'rejected' if reject else 'confirmed'}.",
        )
    kind = "vehicle" if booking.is_vehicle else "venue"
    return redirect(f"{reverse('bookings:keys')}?kind={kind}&tab=confirm")


@administrator_required
def fuel_receipt(request, pk: int):
    """The receipt, shown only to the Admin. Storage URLs are signed and short-lived."""
    handover = get_object_or_404(KeyHandover, pk=pk)
    if not handover.fuel_receipt:
        raise PermissionDenied("No receipt was uploaded for this trip.")
    return redirect(handover.fuel_receipt.url)


# ------------------------------------------------------------------- kiosk


@administrator_required
def kiosk_home(request):
    """Turn this session into the office kiosk and ask for a booking number."""
    if not request.session.get(KIOSK_SESSION_KEY):
        request.session[KIOSK_SESSION_KEY] = True
        log_action(
            actor=request.user,
            action="KIOSK_STARTED",
            entity_type="User",
            entity_id=request.user.pk,
            description="Key kiosk opened on this browser.",
            request=request,
        )
    form = KioskLookupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        booking = find_for_kiosk(form.cleaned_data["reference"])
        if booking is None:
            form.add_error("reference", "No booking has that number. Check it and try again.")
        else:
            return redirect("bookings:kiosk_booking", reference=booking.booking_reference)
    return render(
        request,
        "bookings/kiosk.html",
        {"form": form, "step": "lookup", "today": kiosk_today(), "done": request.GET.get("done")},
    )


@administrator_required
def kiosk_booking(request, reference: str):
    booking = find_by_reference(reference)
    if booking is None:
        flash.error(request, "No booking has that number.")
        return redirect("bookings:kiosk")
    handover = KeyHandover.objects.filter(booking=booking).first()
    if handover and handover.returned_at:
        action = "done"
    elif handover and handover.issued_at:
        action = "return"
    else:
        action = "issue"

    form = None
    if action == "issue":
        form = IssueKeyForm(request.POST or None, vehicle=booking.is_vehicle)
    elif action == "return":
        form = ReturnKeyForm(
            request.POST or None, request.FILES or None, vehicle=booking.is_vehicle
        )
    if request.method == "POST" and form is not None and form.is_valid():
        done = (_do_issue if action == "issue" else _do_return)(
            request, booking, form, Via.KIOSK
        )
        if done:
            return redirect(f"{reverse('bookings:kiosk')}?done={action}")
    return render(
        request,
        "bookings/kiosk.html",
        {
            "step": action,
            "booking": booking,
            "handover": handover,
            "form": form,
        },
    )


@administrator_required
def kiosk_exit(request):
    """Leaving the kiosk needs the Admin's password, typed at the PC."""
    form = KioskExitForm(request.POST or None)
    if request.method == "POST" and is_throttled(request, "login", request.user.email):
        return render(request, "accounts/throttled.html", status=429)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request, username=request.user.email, password=form.cleaned_data["password"]
        )
        if user is None or user.pk != request.user.pk:
            form.add_error("password", "That password is not right.")
        else:
            request.session.pop(KIOSK_SESSION_KEY, None)
            log_action(
                actor=request.user,
                action="KIOSK_CLOSED",
                entity_type="User",
                entity_id=request.user.pk,
                description="Key kiosk closed on this browser.",
                request=request,
            )
            return redirect("bookings:keys")
    return render(request, "bookings/kiosk.html", {"form": form, "step": "exit"})
