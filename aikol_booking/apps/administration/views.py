"""Administrator screens: dashboard, users, settings, site content, on behalf."""

from __future__ import annotations

import datetime as dt

from django.contrib import messages as flash
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User
from apps.audit.services import log_action
from apps.bookings.keys import keys_awaiting_collection, outstanding_keys
from apps.bookings.models import BLOCKING_STATUSES, Booking, BookingStatus
from apps.resources.models import Resource, ResourceStatus

from .forms import (
    AnnouncementForm,
    EmailConfigurationForm,
    SiteContentForm,
    SystemSettingForm,
    UserAdminForm,
)
from .models import Announcement, SiteContent, SystemSetting
from apps.notifications.models import EmailConfiguration, EmailOutbox, EmailStatus

PAGE_SIZE = 20


def _pagination_context(request, page) -> dict:
    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()
    return {
        "querystring": f"{querystring}&" if querystring else "",
        "page_range": page.paginator.get_elided_page_range(
            page.number, on_each_side=2, on_ends=1
        ),
    }


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
    context = {"page": page, "q": term, "role": role or "", "state": state or ""}
    context.update(_pagination_context(request, page))
    return render(
        request,
        "administration/users.html",
        context,
    )


@administrator_required
def user_edit(request, pk: int):
    person = get_object_or_404(User, pk=pk)
    form = UserAdminForm(request.POST or None, instance=person)
    if request.method == "POST" and form.is_valid():
        original = User.objects.only("is_active", "email_verified").get(pk=pk)
        was_active = original.is_active
        was_verified = original.email_verified
        person = form.save(commit=False)
        if person.email_verified and not was_verified:
            person.email_verified_at = timezone.now()
        elif not person.email_verified:
            person.email_verified_at = None
        person.save()
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
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return HttpResponse(status=204)
        return redirect("administration:users")
    return render(
        request,
        "administration/user_edit.html",
        {
            "person": person,
            "form": form,
            "bookings": person.bookings.count(),
            "totp_device": getattr(person, "totp_device", None),
        },
    )


@administrator_required
def user_delete(request, pk: int):
    """Two gates, as for a resource: the account must already be retired, and
    nothing in the booking record may refer to it. The second is enforced by
    the database (PROTECT); the screen says which gate stopped it."""
    person = get_object_or_404(User, pk=pk)
    if person.pk == request.user.pk:
        flash.error(request, "You cannot delete your own account.")
        return redirect("administration:user_edit", pk=pk)
    history = (
        Booking.objects.filter(Q(user=person) | Q(created_by=person) | Q(decided_by=person)).count()
    )
    if request.method == "POST" and not person.is_active and not history:
        email = person.email
        try:
            person.delete()
        except ProtectedError:
            flash.error(request, f"{email} appears in booking or key records and cannot be deleted.")
            return redirect("administration:user_edit", pk=pk)
        log_action(
            actor=request.user,
            action="USER_DELETED",
            entity_type="User",
            entity_id=pk,
            description="Account deleted; it had no booking history.",
            request=request,
        )
        flash.success(request, f"{email} deleted.")
        return redirect("administration:users")
    return render(
        request,
        "administration/user_delete.html",
        {"person": person, "history": history},
    )


@administrator_required
@require_POST
def user_mfa_reset(request, pk: int):
    """For a person whose phone and recovery codes are both gone.

    Deleting the device is what invalidates their verified sessions — the
    middleware checks the device id, not a flag. An administrator may not reset
    their own: that is what recovery codes are for, and a self-reset would turn
    a stolen session into a stolen account.
    """
    person = get_object_or_404(User, pk=pk)
    if person.pk == request.user.pk:
        raise PermissionDenied("Use a recovery code, or ask another administrator.")
    device = getattr(person, "totp_device", None)
    if device is not None:
        device.delete()
        person.recovery_codes.all().delete()
        log_action(
            actor=request.user,
            action="USER_MFA_RESET",
            entity_type="User",
            entity_id=person.pk,
            description=f"Authenticator reset for {person.full_name}; they must enrol again.",
            request=request,
        )
        flash.success(request, f"{person.full_name} will set up a new authenticator at their next sign-in.")
    else:
        flash.info(request, f"{person.full_name} has no authenticator to reset.")
    return redirect("administration:user_edit", pk=pk)


@administrator_required
def settings_list(request):
    """Business rules live here, not in the code, so AIKOL can change a limit
    without a software release."""
    SystemSetting.seed()
    # Alphabetical by label, except that the day's start reads before its end.
    rows = sorted(
        SystemSetting.objects.all(),
        key=lambda row: (row.label.replace("Day ends", "Day starts~"), row.key),
    )
    email_configuration = EmailConfiguration.load()
    queued_email_count = EmailOutbox.objects.filter(
        status__in=(EmailStatus.PENDING, EmailStatus.FAILED), attempts__lt=5
    ).count()
    email_form = EmailConfigurationForm(instance=email_configuration, prefix="email")
    if request.method == "POST":
        if request.POST.get("form_kind") == "email":
            email_form = EmailConfigurationForm(
                request.POST,
                instance=email_configuration,
                prefix="email",
            )
            if email_form.is_valid():
                email_form.save()
                log_action(
                    actor=request.user,
                    action="EMAIL_CONFIGURATION_CHANGED",
                    entity_type="EmailConfiguration",
                    entity_id=1,
                    description="Email delivery configuration changed; secrets omitted.",
                    request=request,
                )
                flash.success(request, "Email delivery settings saved.")
                return redirect("administration:settings")
            flash.error(request, "Email delivery settings were not accepted.")
            return render(
                request,
                "administration/settings.html",
                {
                    "rows": rows,
                    "email_form": email_form,
                    "email_configuration": email_configuration,
                    "queued_email_count": queued_email_count,
                },
            )
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
            flash.success(request, f"{setting.label} set to {setting.display_value}.")
            return redirect("administration:settings")
        flash.error(request, "That value was not accepted.")
    return render(
        request,
        "administration/settings.html",
        {
            "rows": rows,
            "email_form": email_form,
            "email_configuration": email_configuration,
            "queued_email_count": queued_email_count,
        },
    )


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
    return render(
        request,
        "administration/site_content.html",
        {"form": form, "announcements": Announcement.objects.all()},
    )


@administrator_required
def announcement_new(request):
    form = AnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        announcement = form.save()
        log_action(
            actor=request.user,
            action="ANNOUNCEMENT_CREATED",
            entity_type="Announcement",
            entity_id=announcement.pk,
            description=f"Announcement created: {announcement.title}.",
            request=request,
        )
        flash.success(request, "Announcement published.")
        return redirect("administration:site_content")
    return render(
        request,
        "administration/announcement_form.html",
        {"form": form, "announcement": None},
    )


@administrator_required
def announcement_edit(request, pk: int):
    announcement = get_object_or_404(Announcement, pk=pk)
    form = AnnouncementForm(request.POST or None, instance=announcement)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_action(
            actor=request.user,
            action="ANNOUNCEMENT_UPDATED",
            entity_type="Announcement",
            entity_id=announcement.pk,
            description=f"Announcement updated: {announcement.title}.",
            request=request,
        )
        flash.success(request, "Announcement saved.")
        return redirect("administration:site_content")
    return render(
        request,
        "administration/announcement_form.html",
        {"form": form, "announcement": announcement},
    )


def _parse_date(raw):
    """A date from the query string, or None when it is missing or malformed."""
    try:
        return dt.date.fromisoformat((raw or "").strip())
    except ValueError:
        return None


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
    date_from = _parse_date(request.GET.get("from"))
    date_to = _parse_date(request.GET.get("to"))
    if date_from:
        entries = entries.filter(created_at__date__gte=date_from)
    if date_to:
        entries = entries.filter(created_at__date__lte=date_to)
    page = Paginator(entries.order_by("-created_at", "-pk"), PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    # BOOKING_APPROVED reads as "Booking approved" in the filter.
    actions = [
        (code, code.replace("_", " ").capitalize())
        for code in AuditLog.objects.values_list("action", flat=True)
        .distinct()
        .order_by("action")
    ]
    context = {
        "page": page,
        "q": term,
        "action": action or "",
        "actions": actions,
        "date_from": date_from,
        "date_to": date_to,
    }
    context.update(_pagination_context(request, page))
    return render(
        request,
        "administration/audit.html",
        context,
    )
