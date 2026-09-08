"""Booking submission, history, cancellation and the approvals queue."""

from __future__ import annotations

import datetime as dt

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.services import log_action
from apps.resources.models import Resource, ResourceStatus, ResourceType, Vehicle, Venue

from .forms import BookingForm, CancellationForm, DecisionForm, RecurrenceForm
from .models import BLOCKING_STATUSES, AcademicTerm, Booking, BookingStatus
from .services import (
    approve_booking,
    approve_series,
    cancel_booking,
    cancel_series,
    create_booking,
    create_series,
    find_conflicts,
    plan_series,
)

PAGE_SIZE = 15


def approver_required(view):
    """Deciding bookings is the approver's authority (decision 5). An
    administrator has it too; an ordinary user gets 403, not a hidden link."""

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Sign in first.")
        if not request.user.is_approver:
            raise PermissionDenied("Only an approver or administrator may decide bookings.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _must_be_able_to_book(user) -> None:
    if not user.can_book:
        raise PermissionDenied(
            "Confirm your email address before making a booking."
        )


def _specific(resource: Resource) -> Resource:
    """The Venue or Vehicle row, so its own fields are reachable."""
    if resource.resource_type == ResourceType.VENUE:
        return Venue.objects.get(pk=resource.pk)
    if resource.resource_type == ResourceType.VEHICLE:
        return Vehicle.objects.get(pk=resource.pk)
    return resource


# ------------------------------------------------------------- availability


@login_required
def availability(request, pk: int):
    """What is already taken, for a chosen day.

    Rendered on the server. The browser's own check is a convenience layered on
    top of this and is never what decides anything.
    """
    resource = _specific(get_object_or_404(Resource, pk=pk))
    try:
        day = dt.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = timezone.localdate()

    start = timezone.make_aware(dt.datetime.combine(day, dt.time.min))
    end = start + dt.timedelta(days=1)
    taken = (
        Booking.objects.filter(
            resource=resource, status__in=BLOCKING_STATUSES, start_at__lt=end, end_at__gt=start
        )
        .select_related("resource")
        .order_by("start_at")
    )
    return render(
        request,
        "bookings/availability.html",
        {
            "resource": resource,
            "day": day,
            "weekday": day.strftime("%A"),
            "taken": taken,
            "previous": day - dt.timedelta(days=1),
            "next": day + dt.timedelta(days=1),
        },
    )


# ---------------------------------------------------------------- creating


@login_required
def booking_create(request, pk: int):
    _must_be_able_to_book(request.user)
    resource = _specific(get_object_or_404(Resource, pk=pk))
    if resource.status != ResourceStatus.ACTIVE:
        flash.error(request, f"{resource.name} is not available for booking.")
        return redirect("resources:detail", pk=pk)

    form = BookingForm(request.POST or None, resource=resource, user=request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        extra = {}
        if resource.resource_type == ResourceType.VEHICLE:
            extra = {
                "driver_arrangement": data["driver_arrangement"],
                "location_from": data["location_from"],
                "location_to": data["location_to"],
                "passengers": data["passengers"],
            }
        else:
            extra = {"attendees": data["attendees"]}
        try:
            booking = create_booking(
                resource=resource,
                user=request.user,
                created_by=request.user,
                start_at=data["start_at"],
                end_at=data["end_at"],
                purpose=data["purpose"],
                **extra,
            )
        except ValidationError as exc:
            for problem in exc.messages:
                form.add_error(None, problem)
        else:
            flash.success(
                request,
                f"Request {booking.booking_reference} submitted. "
                "You will be emailed once it is decided.",
            )
            return redirect("bookings:detail", pk=booking.pk)

    return render(
        request,
        "bookings/create.html",
        {
            "resource": resource,
            "form": form,
            "is_vehicle": resource.resource_type == ResourceType.VEHICLE,
        },
    )


@login_required
def series_create(request, pk: int):
    """A weekly series, for a semester of classes.

    Two passes. The first shows exactly what would be created and what would be
    left out; only then may the requester accept a partial series. Nothing is
    ever dropped without being shown first.
    """
    _must_be_able_to_book(request.user)
    resource = _specific(get_object_or_404(Resource, pk=pk))
    if resource.resource_type != ResourceType.VENUE:
        flash.error(request, "Recurring bookings are for rooms. A car is booked per trip.")
        return redirect("resources:detail", pk=pk)

    form = RecurrenceForm(request.POST or None)
    plan = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            plan = plan_series(
                resource=resource,
                term=data["term"],
                weekday_times=data["weekday_times"],
                starts_on=data["starts_on"],
                repeat_until=data["repeat_until"],
            )
        except ValidationError as exc:
            for problem in exc.messages:
                form.add_error(None, problem)
        else:
            wants_partial = data["accept_partial"]
            if plan["clashing"] and not wants_partial:
                flash.warning(
                    request,
                    f"{len(plan['clashing'])} of these dates are already reserved. "
                    "They are listed below. Tick the box to create the rest.",
                )
            else:
                try:
                    series, created, plan = create_series(
                        resource=resource,
                        user=request.user,
                        created_by=request.user,
                        term=data["term"],
                        weekday_times=data["weekday_times"],
                        starts_on=data["starts_on"],
                        repeat_until=data["repeat_until"],
                        purpose=data["purpose"],
                        accept_partial=wants_partial,
                    )
                except ValidationError as exc:
                    for problem in exc.messages:
                        form.add_error(None, problem)
                else:
                    flash.success(
                        request,
                        f"{len(created)} bookings requested for {resource.name}.",
                    )
                    return redirect("bookings:mine")

    return render(
        request,
        "bookings/series_create.html",
        {"resource": resource, "form": form, "plan": plan, "terms": AcademicTerm.objects.all()},
    )


# ----------------------------------------------------------------- reading


@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).select_related("resource", "series")
    status = request.GET.get("status")
    if status in BookingStatus.values:
        bookings = bookings.filter(status=status)
    when = request.GET.get("when")
    if when == "upcoming":
        bookings = bookings.filter(end_at__gte=timezone.now())
    elif when == "past":
        bookings = bookings.filter(end_at__lt=timezone.now())

    page = Paginator(bookings.order_by("-start_at", "-pk"), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    counts = {
        "total": Booking.objects.filter(user=request.user).count(),
        "pending": Booking.objects.filter(user=request.user, status=BookingStatus.PENDING).count(),
        "approved": Booking.objects.filter(
            user=request.user, status=BookingStatus.APPROVED
        ).count(),
        "upcoming": Booking.objects.filter(
            user=request.user, status__in=BLOCKING_STATUSES, start_at__gte=timezone.now()
        ).count(),
    }
    return render(
        request,
        "bookings/mine.html",
        {"page": page, "counts": counts, "status": status or "", "when": when or ""},
    )


@login_required
def booking_detail(request, pk: int):
    booking = get_object_or_404(
        Booking.objects.select_related("resource", "user", "created_by", "series"), pk=pk
    )
    # Ownership is checked on the object, never inferred from the URL.
    if booking.user != request.user and not request.user.is_approver:
        raise PermissionDenied("That booking is not yours.")
    return render(
        request,
        "bookings/detail.html",
        {
            "booking": booking,
            "can_cancel": booking.can_be_cancelled_by(request.user),
            "is_vehicle": booking.resource.resource_type == ResourceType.VEHICLE,
        },
    )


# ------------------------------------------------------------- cancelling


@login_required
def booking_cancel(request, pk: int):
    booking = get_object_or_404(Booking, pk=pk)
    if booking.user != request.user and not request.user.is_approver:
        raise PermissionDenied("That booking is not yours.")

    form = CancellationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_booking(
                booking, cancelled_by=request.user, reason=form.cleaned_data["reason"]
            )
        except ValidationError as exc:
            for problem in exc.messages:
                form.add_error(None, problem)
        else:
            log_action(
                actor=request.user,
                action="BOOKING_CANCELLED",
                entity_type="Booking",
                entity_id=booking.pk,
                description=f"{booking.booking_reference} cancelled.",
                request=request,
            )
            flash.success(request, f"{booking.booking_reference} cancelled.")
            return redirect("bookings:mine")

    return render(
        request,
        "bookings/cancel.html",
        {"booking": booking, "form": form, "allowed": booking.can_be_cancelled_by(request.user)},
    )


@login_required
def series_cancel(request, pk: int):
    from .models import BookingSeries

    series = get_object_or_404(BookingSeries, pk=pk)
    if series.user != request.user and not request.user.is_approver:
        raise PermissionDenied("That series is not yours.")

    form = CancellationForm(request.POST or None)
    future = series.bookings.filter(status__in=BLOCKING_STATUSES, start_at__gt=timezone.now())
    if request.method == "POST" and form.is_valid():
        count = cancel_series(
            series, cancelled_by=request.user, reason=form.cleaned_data["reason"]
        )
        log_action(
            actor=request.user,
            action="SERIES_CANCELLED",
            entity_type="BookingSeries",
            entity_id=series.pk,
            description=f"{count} future occurrences cancelled.",
            request=request,
        )
        flash.success(request, f"{count} future bookings cancelled. Past ones are unchanged.")
        return redirect("bookings:mine")

    return render(
        request,
        "bookings/series_cancel.html",
        {"series": series, "form": form, "future": future},
    )


# ------------------------------------------------------------- approvals


@approver_required
def approvals(request):
    pending = (
        Booking.objects.filter(status=BookingStatus.PENDING)
        .select_related("resource", "user", "series")
        .order_by("start_at", "pk")
    )
    kind = request.GET.get("kind")
    if kind in ResourceType.values:
        pending = pending.filter(resource__resource_type=kind)
    term = (request.GET.get("q") or "").strip()
    if term:
        pending = pending.filter(
            Q(booking_reference__icontains=term)
            | Q(user__full_name__icontains=term)
            | Q(resource__name__icontains=term)
        )
    page = Paginator(pending, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request, "bookings/approvals.html", {"page": page, "kind": kind or "", "q": term}
    )


@approver_required
def decide(request, pk: int):
    booking = get_object_or_404(
        Booking.objects.select_related("resource", "user", "series"), pk=pk
    )
    form = DecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reason = form.cleaned_data["reason"]
        action = request.POST.get("action")
        try:
            if action == "approve":
                approve_booking(booking, decided_by=request.user, reason=reason)
                flash.success(request, f"{booking.booking_reference} approved.")
            elif action == "reject":
                reject_from_view(booking, request.user, reason)
                flash.success(request, f"{booking.booking_reference} rejected.")
            else:
                raise ValidationError("Choose approve or reject.")
        except ValidationError as exc:
            for problem in exc.messages:
                form.add_error(None, problem)
        else:
            log_action(
                actor=request.user,
                action=f"BOOKING_{action.upper()}D",
                entity_type="Booking",
                entity_id=booking.pk,
                description=f"{booking.booking_reference} {action}d.",
                request=request,
            )
            return redirect("bookings:approvals")

    # Shown alongside the decision: what else is already approved for this
    # resource at this time. An approver should not have to go and look.
    overlapping = find_conflicts(
        booking.resource_id, booking.start_at, booking.end_at, exclude_pk=booking.pk
    ).select_related("user")
    return render(
        request,
        "bookings/decide.html",
        {"booking": booking, "form": form, "overlapping": overlapping},
    )


def reject_from_view(booking, user, reason: str):
    from .services import reject_booking

    return reject_booking(booking, decided_by=user, reason=reason)


@approver_required
def decide_series(request, pk: int):
    from .models import BookingSeries

    series = get_object_or_404(BookingSeries, pk=pk)
    form = DecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        approved, refused = approve_series(
            series, decided_by=request.user, reason=form.cleaned_data["reason"]
        )
        log_action(
            actor=request.user,
            action="SERIES_APPROVED",
            entity_type="BookingSeries",
            entity_id=series.pk,
            description=f"{len(approved)} approved, {len(refused)} refused.",
            request=request,
        )
        if refused:
            flash.warning(
                request,
                f"{len(approved)} occurrences approved. {len(refused)} could not be — "
                "their periods were taken after the series was requested.",
            )
        else:
            flash.success(request, f"All {len(approved)} occurrences approved.")
        return redirect("bookings:approvals")

    return render(
        request,
        "bookings/decide_series.html",
        {
            "series": series,
            "form": form,
            "occurrences": series.bookings.order_by("start_at"),
        },
    )
