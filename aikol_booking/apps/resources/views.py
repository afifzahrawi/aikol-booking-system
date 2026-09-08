"""Browsing and management for venues, vehicles and facilities.

Authorisation is checked in every view and returns 403. A hidden menu item is
not a permission check — anyone can type a URL.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Prefetch, Q, QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.services import log_action

from .forms import FacilityForm, ResourceImageForm, VehicleForm, VenueForm
from .models import (
    Facility,
    Resource,
    ResourceImage,
    ResourceStatus,
    ResourceType,
    Vehicle,
    Venue,
)
from .services import DeletionRefused, delete_resource, reorder_facilities

PAGE_SIZE = 12


def administrator_required(view):
    """403 rather than a redirect: the person is signed in, they simply may not
    do this, and pretending the page does not exist would be a lie."""

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Sign in first.")
        if not request.user.is_administrator:
            raise PermissionDenied("Only an administrator may manage resources.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _filtered(queryset: QuerySet, request, *, search_fields: tuple[str, ...]) -> QuerySet:
    """Filter and search IN THE QUERY. A list view never loads a whole table to
    render one page of it."""
    term = (request.GET.get("q") or "").strip()
    if term:
        matches = Q()
        for field in search_fields:
            matches |= Q(**{f"{field}__icontains": term})
        queryset = queryset.filter(matches)
    status = request.GET.get("status")
    if status in ResourceStatus.values:
        queryset = queryset.filter(status=status)
    facility = request.GET.get("facility")
    if facility:
        queryset = queryset.filter(facilities__pk=facility)
    return queryset.distinct()


def _paginated(request, queryset, template: str, extra: dict | None = None):
    from django.core.paginator import Paginator

    # A page of an unordered queryset can repeat or skip rows at the boundary.
    # `annotate()` drops a model's default ordering, so this is not merely
    # belt-and-braces — it is what keeps the annotated management lists correct.
    if not queryset.ordered:
        queryset = queryset.order_by("name", "pk")
    page = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))
    # Carry the filters into the pager links. Without this, page 2 of a
    # filtered list is page 2 of the whole table.
    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()
    context = {
        "page": page,
        "querystring": f"{querystring}&" if querystring else "",
        "q": request.GET.get("q", ""),
        "status": request.GET.get("status", ""),
        "facility": request.GET.get("facility", ""),
        "facilities": Facility.objects.filter(is_active=True),
    }
    context.update(extra or {})
    return render(request, template, context)


# --------------------------------------------------------------- browsing


def _bookable_images() -> Prefetch:
    return Prefetch("images", queryset=ResourceImage.objects.order_by("display_order", "id"))


@login_required
def venue_list(request):
    venues = _filtered(
        Venue.objects.filter(status=ResourceStatus.ACTIVE)
        .prefetch_related(_bookable_images(), "facilities"),
        request,
        search_fields=("name", "code", "location"),
    )
    return _paginated(request, venues, "resources/venue_list.html")


@login_required
def vehicle_list(request):
    # An untaxed car is withdrawn here rather than shown and then refused at the
    # booking form. The requester never learns why; that is an office matter.
    from django.utils import timezone

    vehicles = _filtered(
        Vehicle.objects.filter(
            status=ResourceStatus.ACTIVE, road_tax_expiry__gte=timezone.localdate()
        ).prefetch_related(_bookable_images(), "facilities"),
        request,
        search_fields=("name", "code", "make", "model", "registration_number"),
    )
    return _paginated(request, vehicles, "resources/vehicle_list.html")


@login_required
def resource_detail(request, pk: int):
    resource = get_object_or_404(
        Resource.objects.prefetch_related(_bookable_images(), "facilities"), pk=pk
    )
    specific = resource
    if resource.resource_type == ResourceType.VENUE:
        specific = get_object_or_404(Venue, pk=pk)
    elif resource.resource_type == ResourceType.VEHICLE:
        specific = get_object_or_404(Vehicle, pk=pk)
    return render(
        request,
        "resources/detail.html",
        {
            "resource": specific,
            "is_vehicle": resource.resource_type == ResourceType.VEHICLE,
            # The expiry date itself is administrator-facing only.
            "show_road_tax": request.user.is_administrator,
        },
    )


# ------------------------------------------------------------- management


@administrator_required
def manage_venues(request):
    venues = _filtered(
        Venue.objects.annotate(booking_count=Count("bookings")),
        request,
        search_fields=("name", "code", "location"),
    )
    return _paginated(request, venues, "resources/manage_venues.html")


@administrator_required
def manage_vehicles(request):
    vehicles = _filtered(
        Vehicle.objects.annotate(booking_count=Count("bookings")),
        request,
        search_fields=("name", "code", "make", "model", "registration_number"),
    )
    return _paginated(request, vehicles, "resources/manage_vehicles.html")


def _edit_resource(request, form_class, instance, kind: str, redirect_to: str):
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        created = instance is None or instance.pk is None
        obj = form.save()
        log_action(
            actor=request.user,
            action=f"{kind.upper()}_{'CREATED' if created else 'UPDATED'}",
            entity_type=kind.title(),
            entity_id=obj.pk,
            description=f"{obj.name} ({obj.code}).",
            request=request,
        )
        messages.success(request, f"{obj.name} {'created' if created else 'saved'}.")
        return redirect(redirect_to)
    return render(
        request,
        "resources/edit.html",
        {"form": form, "kind": kind, "instance": instance, "cancel_to": redirect_to},
    )


@administrator_required
def venue_edit(request, pk: int | None = None):
    instance = get_object_or_404(Venue, pk=pk) if pk else None
    return _edit_resource(request, VenueForm, instance, "venue", "resources:manage_venues")


@administrator_required
def vehicle_edit(request, pk: int | None = None):
    instance = get_object_or_404(Vehicle, pk=pk) if pk else None
    return _edit_resource(request, VehicleForm, instance, "vehicle", "resources:manage_vehicles")


@administrator_required
def resource_delete(request, pk: int):
    """Both gates are applied by the service, and the interface says which one
    stopped it rather than simply refusing."""
    resource = get_object_or_404(Resource, pk=pk)
    back = (
        "resources:manage_vehicles"
        if resource.resource_type == ResourceType.VEHICLE
        else "resources:manage_venues"
    )
    if request.method == "POST":
        try:
            name, code = resource.name, resource.code
            delete_resource(resource)
        except DeletionRefused as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(back)
        log_action(
            actor=request.user,
            action="RESOURCE_DELETED",
            entity_type="Resource",
            entity_id=pk,
            description=f"{name} ({code}) deleted; it had no booking history.",
            request=request,
        )
        messages.success(request, f"{name} deleted.")
        return redirect(back)
    return render(
        request,
        "resources/confirm_delete.html",
        {
            "resource": resource,
            "booking_count": resource.bookings.count(),
            "is_active": resource.status == ResourceStatus.ACTIVE,
            "cancel_to": back,
        },
    )


@administrator_required
def resource_images(request, pk: int):
    resource = get_object_or_404(Resource, pk=pk)
    form = ResourceImageForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        image = form.save(commit=False)
        image.resource = resource
        last = resource.images.order_by("-display_order").first()
        image.display_order = (last.display_order + 1) if last else 0
        image.save()
        log_action(
            actor=request.user,
            action="RESOURCE_IMAGE_ADDED",
            entity_type="Resource",
            entity_id=resource.pk,
            description=f"Photograph added to {resource.name}.",
            request=request,
        )
        messages.success(request, "Photograph added.")
        return redirect("resources:images", pk=pk)
    return render(
        request, "resources/images.html", {"resource": resource, "form": form}
    )


@administrator_required
@require_POST
def resource_image_delete(request, pk: int, image_pk: int):
    image = get_object_or_404(ResourceImage, pk=image_pk, resource_id=pk)
    image.delete()
    log_action(
        actor=request.user,
        action="RESOURCE_IMAGE_REMOVED",
        entity_type="Resource",
        entity_id=pk,
        description="Photograph removed.",
        request=request,
    )
    messages.success(request, "Photograph removed.")
    return redirect("resources:images", pk=pk)


# -------------------------------------------------------------- facilities


@administrator_required
def manage_facilities(request):
    facilities = Facility.objects.annotate(usage=Count("resourcefacility")).order_by(
        "display_order", "name"
    )
    term = (request.GET.get("q") or "").strip()
    applies = request.GET.get("applies")
    filtered = bool(term or applies)
    if term:
        facilities = facilities.filter(Q(name__icontains=term) | Q(code__icontains=term))
    if applies:
        facilities = facilities.filter(applies_to=applies)
    return render(
        request,
        "resources/manage_facilities.html",
        {
            "facilities": facilities,
            "q": term,
            "applies": applies or "",
            # Reordering a filtered subset would produce an order nobody saw, so
            # the handles switch off and the page says why.
            "filtered": filtered,
        },
    )


@administrator_required
def facility_edit(request, pk: int | None = None):
    instance = get_object_or_404(Facility, pk=pk) if pk else None
    form = FacilityForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        created = instance is None
        facility = form.save()
        log_action(
            actor=request.user,
            action=f"FACILITY_{'CREATED' if created else 'UPDATED'}",
            entity_type="Facility",
            entity_id=facility.pk,
            description=f"{facility.name} ({facility.code}).",
            request=request,
        )
        messages.success(request, f"{facility.name} {'created' if created else 'saved'}.")
        return redirect("resources:manage_facilities")
    return render(
        request,
        "resources/edit.html",
        {
            "form": form,
            "kind": "facility",
            "instance": instance,
            "cancel_to": "resources:manage_facilities",
        },
    )


@administrator_required
@require_POST
def facility_reorder(request):
    """Accepts the whole visible order and rewrites display_order as 1..n."""
    ids = request.POST.getlist("order[]") or request.POST.get("order", "").split(",")
    try:
        reorder_facilities([i for i in ids if str(i).strip()])
    except (ValidationError, ValueError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    log_action(
        actor=request.user,
        action="FACILITY_REORDERED",
        entity_type="Facility",
        description="Facility display order changed.",
        request=request,
    )
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("resources:manage_facilities")


@administrator_required
@require_POST
def facility_delete(request, pk: int):
    """A facility in use is deactivated, never deleted — the same rule as every
    other record here, and PROTECT on the join enforces it."""
    facility = get_object_or_404(Facility, pk=pk)
    used = facility.resourcefacility_set.count()
    if used:
        messages.error(
            request,
            f'"{facility.name}" is used by {used} resource{"" if used == 1 else "s"} '
            "and cannot be deleted. Deactivate it instead.",
        )
        return redirect("resources:manage_facilities")
    name = facility.name
    facility.delete()
    log_action(
        actor=request.user,
        action="FACILITY_DELETED",
        entity_type="Facility",
        entity_id=pk,
        description=f"{name} deleted; no resource used it.",
        request=request,
    )
    messages.success(request, f"{name} deleted.")
    return redirect("resources:manage_facilities")
