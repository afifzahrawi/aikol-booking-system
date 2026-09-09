"""Registration, verification and sign-in."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic import CreateView

from apps.audit.services import log_action
from apps.notifications.services import queue_email

from .forms import EmailAuthenticationForm, RegistrationForm
from .models import User
from .throttle import is_throttled, reset as reset_throttle
from .tokens import email_verification_token


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:register_done")

    def post(self, request, *args, **kwargs):
        if is_throttled(request, "register", request.POST.get("email", "")):
            return render(request, "accounts/throttled.html", status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """An address that is already registered gets the SAME response as a new
        one, and an email to the existing account instead of a new record.

        Anything else is an address oracle: submit a list, read the error
        messages, learn which of your colleagues has an account here.
        """
        if form.email_already_registered:
            existing = User.objects.get(email__iexact=form.cleaned_data["email"])
            queue_email(
                to=existing.email,
                subject="Somebody tried to register your AIKOL Booking address",
                body=(
                    f"Assalamualaikum {existing.full_name},\n\n"
                    "Somebody submitted the registration form using this address. You already "
                    "have an account, so no new one was created and nothing has changed.\n\n"
                    "If that was you, simply sign in. If you have forgotten your password, use "
                    "the 'Forgotten your password?' link on the sign-in page.\n\n"
                    "If it was not you, you can ignore this message.\n"
                ),
                kind="ACCOUNT_DUPLICATE_ATTEMPT",
            )
            log_action(
                actor=None,
                action="ACCOUNT_REGISTER_DUPLICATE",
                entity_type="User",
                entity_id=existing.pk,
                description="Registration attempted for an address that already has an account.",
                request=self.request,
            )
            return redirect(self.success_url)

        # The account, the audit entry and the verification email are one
        # transaction. An account that exists with no way to verify it is worse
        # than no account.
        with transaction.atomic():
            response = super().form_valid(form)
            user = self.object
            log_action(
                actor=None,
                action="ACCOUNT_REGISTERED",
                entity_type="User",
                entity_id=user.pk,
                description=f"Self-registration for {user.email}.",
                request=self.request,
            )
            _queue_verification(self.request, user)
        return response


def _queue_verification(request, user: User) -> None:
    link = request.build_absolute_uri(
        reverse(
            "accounts:verify",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": email_verification_token.make_token(user),
            },
        )
    )
    days = settings.PASSWORD_RESET_TIMEOUT // 86400
    queue_email(
        to=user.email,
        subject="Confirm your AIKOL Booking account",
        body=(
            f"Assalamualaikum {user.full_name},\n\n"
            "An account has been created for you on the AIKOL Room and Vehicle Booking "
            "System. Confirm this address to activate it:\n\n"
            f"{link}\n\n"
            f"The link is valid for {days} days. Until it is used, the account cannot "
            "make bookings.\n\n"
            "If you did not request this account, ignore this message.\n"
        ),
        kind="ACCOUNT_VERIFY",
    )


def register_done(request):
    return render(request, "accounts/register_done.html")


def verify_email(request, uidb64: str, token: str):
    """Follow the emailed link. Idempotent: a second visit says so rather than
    failing, because people click links twice.

    Throttled per IP, because the token is the only thing between a guesser and
    a verified account, and an unlimited endpoint invites the guess.
    """
    if is_throttled(request, "verify"):
        return render(request, "accounts/throttled.html", status=429)

    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None

    if user is None or not email_verification_token.check_token(user, token):
        return render(request, "accounts/verify_failed.html", status=400)

    if not user.email_verified:
        user.mark_email_verified()
        log_action(
            actor=user,
            action="ACCOUNT_VERIFIED",
            entity_type="User",
            entity_id=user.pk,
            description=f"Email address confirmed for {user.email}.",
            request=request,
        )
    messages.success(request, "Your address is confirmed. You can now sign in and make bookings.")
    return redirect("accounts:login")


class LoginView(auth_views.LoginView):
    form_class = EmailAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if is_throttled(request, "login", request.POST.get("username", "")):
            return render(request, "accounts/throttled.html", status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # Somebody who finally remembers their password should not stay locked
        # out by their own earlier typos.
        reset_throttle("login", form.cleaned_data.get("username", ""))
        return super().form_valid(form)


@login_required
def dashboard(request):
    """The landing page: a greeting, a search that answers in place, and the
    person's own activity.

    The search runs on the SERVER and is a plain GET form, so it works with
    JavaScript switched off and a filtered result is a shareable URL. It answers
    "what is free" — it does not book anything; each result links to the booking
    form, which applies the rules properly.
    """
    import datetime as dt

    from django.utils import timezone

    from apps.administration.models import SystemSetting
    from apps.bookings.models import BLOCKING_STATUSES, Booking, BookingStatus
    from apps.bookings.services import find_conflicts, validate_period
    from apps.resources.models import ResourceStatus, ResourceType, Vehicle, Venue

    window_start = SystemSetting.get("bookable_window_start")
    window_end = SystemSetting.get("bookable_window_end")
    slots = []
    hour, minute = (int(part) for part in window_start.split(":"))
    end_hour, end_minute = (int(part) for part in window_end.split(":"))
    while (hour, minute) <= (end_hour, end_minute):
        slots.append(f"{hour:02d}:{minute:02d}")
        minute += 30
        if minute >= 60:
            minute -= 60
            hour += 1

    today = timezone.localdate()
    kind = request.GET.get("kind") if request.GET.get("kind") in ResourceType.values else "VENUE"
    from_time = request.GET.get("from") or "09:00"
    to_time = request.GET.get("to") or "11:00"
    try:
        search_date = dt.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        search_date = today

    free, problems, searched = [], [], "date" in request.GET
    if searched:
        try:
            start_at = timezone.make_aware(
                dt.datetime.combine(search_date, dt.time.fromisoformat(from_time))
            )
            end_at = timezone.make_aware(
                dt.datetime.combine(search_date, dt.time.fromisoformat(to_time))
            )
        except ValueError:
            problems = ["That is not a valid time."]
        else:
            if end_at <= start_at:
                problems = ["The finish time must be after the start time."]
            else:
                model = Vehicle if kind == ResourceType.VEHICLE else Venue
                pool = model.objects.filter(status=ResourceStatus.ACTIVE)
                if kind == ResourceType.VEHICLE:
                    pool = pool.filter(road_tax_expiry__gte=today)
                for resource in pool:
                    if validate_period(resource, start_at, end_at):
                        continue
                    if not find_conflicts(resource, start_at, end_at).exists():
                        free.append(resource)

    building = request.GET.get("building", "")
    if searched and building:
        free = [r for r in free if getattr(r, "location", "") == building]

    mine = Booking.objects.filter(user=request.user)

    categories = []
    for value, label in Venue.VenueType.choices:
        rooms = Venue.objects.filter(venue_type=value)
        if not rooms.exists():
            continue
        biggest = max(rooms.values_list("capacity", flat=True))
        first = rooms.exclude(image_slug="").first()
        categories.append(
            {
                "value": value,
                "label": label,
                "count": rooms.count(),
                "largest": biggest,
                "available": rooms.filter(status=ResourceStatus.ACTIVE).exists(),
                "slug": first.placeholder if first else "",
            }
        )

    return render(
        request,
        "accounts/dashboard.html",
        {
            "nav": "dashboard",
            "today": today,
            "window_start": window_start,
            "window_end": window_end,
            "slots": slots,
            "kind": kind,
            "search_date": search_date,
            "from_time": from_time,
            "to_time": to_time,
            "searched": searched,
            "free": free,
            "problems": problems,
            "buildings": sorted(
                {v for v in Venue.objects.values_list("location", flat=True) if v}
            ),
            "building": building,
            "room_total": Venue.objects.count(),
            "car_total": Vehicle.objects.count(),
            "next_booking": mine.filter(
                status=BookingStatus.APPROVED, start_at__gte=timezone.now()
            ).select_related("resource").order_by("start_at").first(),
            "first_pending": mine.filter(status=BookingStatus.PENDING)
            .select_related("resource").order_by("start_at").first(),
            "counts": {
                "pending": mine.filter(status=BookingStatus.PENDING).count(),
                "upcoming": mine.filter(
                    status__in=BLOCKING_STATUSES, start_at__gte=timezone.now()
                ).count(),
            },
            "upcoming": mine.filter(
                status__in=BLOCKING_STATUSES, start_at__gte=timezone.now()
            ).select_related("resource").order_by("start_at")[:5],
            "categories": [c for c in categories if c["count"]],
        },
    )
