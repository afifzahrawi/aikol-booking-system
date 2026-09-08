"""Administrator screens: dashboard, users, settings, site content, on behalf."""

from __future__ import annotations

import datetime as dt

from django.contrib import messages as flash
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.services import log_action
from apps.bookings.keys import keys_awaiting_collection, outstanding_keys
from apps.bookings.models import BLOCKING_STATUSES, Booking, BookingStatus
from apps.resources.models import Resource, ResourceStatus

from .forms import SiteContentForm, SystemSettingForm, UserAdminForm
from .models import SiteContent, SystemSetting

PAGE_SIZE = 20


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
def dashboard(request):
    now = timezone.now()
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return render(
        request,
        "administration/dashboard.html",
        {
            "pending": Booking.objects.filter(status=BookingStatus.PENDING).count(),
            "upcoming": Booking.objects.filter(
                status__in=BLOCKING_STATUSES, start_at__gte=now
            ).count(),
            "this_month": Booking.objects.filter(created_at__gte=month).count(),
            "keys_out": outstanding_keys().count(),
            "keys_overdue": outstanding_keys().filter(booking__end_at__lt=now).count(),
            "awaiting_collection": keys_awaiting_collection().count(),
            "resources": Resource.objects.filter(status=ResourceStatus.ACTIVE).count(),
            "users": User.objects.filter(is_active=True).count(),
            "unverified": User.objects.filter(is_active=True, email_verified=False).count(),
            "recent": Booking.objects.select_related("resource", "user").order_by("-created_at")[:8],
        },
    )


@administrator_required
def user_list(request):
    users = User.objects.annotate(booking_count=Count("bookings"))
    term = (request.GET.get("q") or "").strip()
    if term:
        users = users.filter(
            Q(full_name__icontains=term)
            | Q(email__icontains=term)
            | Q(identification_number__icontains=term)
        )
    role = request.GET.get("role")
    if role in Role.values:
        users = users.filter(role=role)
    state = request.GET.get("state")
    if state == "active":
        users = users.filter(is_active=True)
    elif state == "inactive":
        users = users.filter(is_active=False)
    elif state == "unverified":
        users = users.filter(email_verified=False)

    page = Paginator(users.order_by("full_name", "pk"), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "administration/users.html",
        {"page": page, "q": term, "role": role or "", "state": state or ""},
    )


@administrator_required
def user_edit(request, pk: int):
    person = get_object_or_404(User, pk=pk)
    form = UserAdminForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        was_active = User.objects.get(pk=pk).is_active
        form.save()
        if was_active and not person.is_active:
            action, note = "USER_DEACTIVATED", "deactivated"
        elif not was_active and person.is_active:
            action, note = "USER_REACTIVATED", "reactivated"
        else:
            action, note = "USER_UPDATED", "updated"
        log_action(
            actor=request.user,
            action=action,
            entity_type="User",
            entity_id=person.pk,
            # No telephone, matriculation or licence number in the free text.
            description=f"{person.full_name} {note}; role {person.get_role_display()}.",
            request=request,
        )
        flash.success(request, f"{person.full_name} saved.")
        return redirect("administration:users")
    return render(
        request,
        "administration/user_edit.html",
        {"person": person, "form": form, "bookings": person.bookings.count()},
    )


@administrator_required
def settings_list(request):
    """Business rules live here, not in the code, so AIKOL can change a limit
    without a software release."""
    SystemSetting.seed()
    rows = SystemSetting.objects.all()
    if request.method == "POST":
        key = request.POST.get("key")
        setting = get_object_or_404(SystemSetting, key=key)
        form = SystemSettingForm(request.POST, instance=setting)
        if form.is_valid():
            before = SystemSetting.objects.get(pk=setting.pk).value
            form.save()
            log_action(
                actor=request.user,
                action="SETTING_CHANGED",
                entity_type="SystemSetting",
                entity_id=setting.key,
                description=f"{setting.key}: {before} to {setting.value}.",
                request=request,
            )
            flash.success(request, f"{setting.key} set to {setting.value}.")
            return redirect("administration:settings")
        flash.error(request, "That value was not accepted.")
    return render(request, "administration/settings.html", {"rows": rows})


@administrator_required
def site_content(request):
    content = SiteContent.load()
    form = SiteContentForm(request.POST or None, request.FILES or None, instance=content)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_action(
            actor=request.user,
            action="SITE_CONTENT_UPDATED",
            entity_type="SiteContent",
            entity_id=1,
            description="Header and footer content changed.",
            request=request,
        )
        flash.success(request, "Site content saved.")
        return redirect("administration:site_content")
    return render(request, "administration/site_content.html", {"form": form})


@administrator_required
def audit_log(request):
    """Append-only. This screen reads it and offers nothing that writes."""
    from apps.audit.models import AuditLog

    entries = AuditLog.objects.select_related("actor")
    term = (request.GET.get("q") or "").strip()
    if term:
        entries = entries.filter(
            Q(action__icontains=term)
            | Q(actor_email__icontains=term)
            | Q(description__icontains=term)
        )
    action = request.GET.get("action")
    if action:
        entries = entries.filter(action=action)
    page = Paginator(entries.order_by("-created_at", "-pk"), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    actions = (
        AuditLog.objects.values_list("action", flat=True).distinct().order_by("action")
    )
    return render(
        request,
        "administration/audit.html",
        {"page": page, "q": term, "action": action or "", "actions": actions},
    )
