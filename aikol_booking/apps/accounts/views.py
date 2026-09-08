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
from .tokens import email_verification_token


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:register_done")

    def form_valid(self, form):
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
    failing, because people click links twice."""
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


@login_required
def dashboard(request):
    """A placeholder landing page for Phase 3.

    It exists so that authentication has somewhere to succeed to. The real
    dashboard arrives with the booking screens in Phase 5.
    """
    return render(request, "accounts/dashboard.html")
