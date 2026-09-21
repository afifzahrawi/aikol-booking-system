"""Registration, verification and sign-in."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.generic import CreateView

from apps.audit.services import log_action
from apps.notifications.services import queue_email

from .forms import EmailAuthenticationForm, ProfileForm, RegistrationForm, SecondFactorForm
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
            "An account has been created for you on the AIKOL Venue and Vehicle Booking "
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


class PasswordResetView(auth_views.PasswordResetView):
    """Django's reset view behind the same two-bucket limit as sign-in.

    The limit was defined with the others and never applied, because the URL
    pointed at Django's view directly. Without it the form is a free way to
    fill a person's inbox and to keep the outbox busy."""

    def post(self, request, *args, **kwargs):
        if is_throttled(request, "password_reset", request.POST.get("email", "").lower()):
            return render(request, "accounts/throttled.html", status=429)
        return super().post(request, *args, **kwargs)


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
def profile_edit(request):
    """Let a person maintain contact details without changing governed records.

    Email changes require fresh verification. Affiliation, role and
    matriculation/staff number are maintained by the Kulliyyah office.
    """
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        changed = list(form.changed_data)
        email_changed = "email" in changed
        with transaction.atomic():
            person = form.save(commit=False)
            if email_changed:
                person.email_verified = False
                person.email_verified_at = None
            person.save()
            if email_changed:
                _queue_verification(request, person)
            if changed:
                log_action(
                    actor=person,
                    action="PROFILE_UPDATED",
                    entity_type="User",
                    entity_id=person.pk,
                    # Contact details are personal data and never belong in the
                    # audit log's free-text description.
                    description="Own profile updated: " + ", ".join(changed) + ".",
                    request=request,
                )
        if email_changed:
            messages.success(
                request,
                "Profile updated. Confirm the link sent to your new email address "
                "before making another booking.",
            )
        elif changed:
            messages.success(request, "Your profile has been updated.")
        else:
            messages.info(request, "Your profile is already up to date.")
        return redirect("accounts:profile")

    return render(request, "accounts/profile.html", {"form": form})


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

    from apps.administration.models import Announcement, SystemSetting
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
    try:
        return_date = dt.date.fromisoformat(request.GET.get("end_date", ""))
    except ValueError:
        return_date = search_date

    free, problems, searched = [], [], "date" in request.GET
    if searched:
        try:
            start_at = timezone.make_aware(
                dt.datetime.combine(search_date, dt.time.fromisoformat(from_time))
            )
            end_at = timezone.make_aware(
                dt.datetime.combine(
                    return_date if kind == ResourceType.VEHICLE else search_date,
                    dt.time.fromisoformat(to_time),
                )
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
    if searched and building and kind == ResourceType.VENUE:
        free = [r for r in free if getattr(r, "location", "") == building]

    mine = Booking.objects.filter(user=request.user)

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
            "return_date": return_date,
            "from_time": from_time,
            "to_time": to_time,
            "searched": searched,
            "free": free,
            "problems": problems,
            "buildings": sorted(
                {v for v in Venue.objects.values_list("location", flat=True) if v}
            ),
            "building": building,
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
            "announcements": Announcement.objects.filter(is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=timezone.now()))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=timezone.now()))
            .order_by("-tone", "-created_at"),
        },
    )


# --- Second factor -----------------------------------------------------------
#
# Both views are reachable while MfaRequiredMiddleware is holding the person at
# the door; everything else is not. `next` is honoured only when it is a local
# path, as Django's own login view does.


def _safe_next(request) -> str:
    from django.utils.http import url_has_allowed_host_and_scheme

    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return candidate
    return reverse("accounts:dashboard")


@login_required
def mfa_enrol(request):
    """Show a fresh secret, prove the app has it, then hand over recovery codes."""
    from config.middleware import MfaRequiredMiddleware

    from . import mfa
    from .models import RecoveryCode, TotpDevice

    device = getattr(request.user, "totp_device", None)
    if device is not None and device.confirmed:
        return redirect("accounts:mfa_verify")
    if device is None:
        device = TotpDevice(user=request.user)
        device.set_secret(mfa.generate_secret())
        device.save()

    form = SecondFactorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if is_throttled(request, "mfa", request.user.email):
            return render(request, "accounts/throttled.html", status=429)
        step = mfa.verify(device.secret, form.cleaned_data["code"], after_step=device.last_used_step)
        if step is None:
            form.add_error("code", "That code did not match. Check the app and try again.")
        else:
            with transaction.atomic():
                device.confirmed_at = timezone.now()
                device.last_used_step = step
                device.save(update_fields=["confirmed_at", "last_used_step"])
                codes = RecoveryCode.issue(request.user)
                log_action(
                    actor=request.user, action="MFA_ENROLLED", entity_type="User",
                    entity_id=request.user.pk,
                    description=f"{request.user.full_name} enrolled an authenticator app.",
                    request=request,
                )
            reset_throttle("mfa", request.user.email)
            MfaRequiredMiddleware.mark_verified(request, device)
            return render(request, "accounts/mfa_codes.html", {
                "codes": codes, "next": _safe_next(request), "mfa_gate": True,
            })

    secret = device.secret
    uri = mfa.provisioning_uri(secret, request.user.email, settings.MFA_ISSUER)
    return render(request, "accounts/mfa_enrol.html", {
        "form": form,
        "qr_svg": mfa.qr_svg(uri),
        "manual_key": mfa.grouped(secret),
        "issuer": settings.MFA_ISSUER,
        "next": _safe_next(request),
        "mfa_gate": True,
    })


@login_required
def mfa_verify(request):
    """The second step of signing in, every session."""
    from config.middleware import MfaRequiredMiddleware

    from . import mfa
    from .models import RecoveryCode

    device = getattr(request.user, "totp_device", None)
    if device is None or not device.confirmed:
        return redirect("accounts:mfa_enrol")
    if MfaRequiredMiddleware.verified(request):
        return redirect(_safe_next(request))

    form = SecondFactorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if is_throttled(request, "mfa", request.user.email):
            return render(request, "accounts/throttled.html", status=429)
        code = form.cleaned_data["code"]
        step = mfa.verify(device.secret, code, after_step=device.last_used_step)
        if step is not None:
            device.last_used_step = step
            device.save(update_fields=["last_used_step"])
        elif RecoveryCode.redeem(request.user, code):
            remaining = RecoveryCode.objects.filter(user=request.user, used_at__isnull=True).count()
            log_action(
                actor=request.user, action="MFA_RECOVERY_CODE_USED", entity_type="User",
                entity_id=request.user.pk,
                description=f"{request.user.full_name} signed in with a recovery code; "
                            f"{remaining} left.",
                request=request,
            )
            messages.warning(
                request,
                f"You signed in with a recovery code. {remaining} remain. If your phone is gone, "
                "ask the Kulliyyah office to reset your authenticator so you can enrol a new one.",
            )
        else:
            form.add_error("code", "That code did not match.")
            return render(request, "accounts/mfa_verify.html", {"form": form, "next": _safe_next(request), "mfa_gate": True})
        reset_throttle("mfa", request.user.email)
        MfaRequiredMiddleware.mark_verified(request, device)
        return redirect(_safe_next(request))

    return render(request, "accounts/mfa_verify.html", {
        "form": form, "next": _safe_next(request), "mfa_gate": True,
    })
