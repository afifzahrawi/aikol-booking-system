"""Small security headers that are not provided by Django's middleware."""

from urllib.parse import urlsplit

from django.conf import settings


class SecurityPolicyMiddleware:
    """Apply a deny-by-default browser policy to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        media_origin = getattr(settings, "MEDIA_URL", "")
        image_sources = ["'self'", "data:"]
        if media_origin.startswith("https://"):
            parsed_media = urlsplit(media_origin)
            image_sources.append(f"{parsed_media.scheme}://{parsed_media.netloc}")
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(
                (
                    "default-src 'self'",
                    "base-uri 'self'",
                    "connect-src 'self'",
                    "font-src 'self'",
                    f"img-src {' '.join(image_sources)}",
                    "object-src 'none'",
                    "script-src 'self'",
                    "style-src 'self'",
                    "form-action 'self'",
                    "frame-ancestors 'none'",
                    "upgrade-insecure-requests",
                )
            ),
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response


class MfaRequiredMiddleware:
    """Nobody with authority reaches a screen until their second factor is done.

    A middleware rather than another decorator, because the role decorators are
    repeated in seven modules and a screen that forgot one would also forget
    this. Here there is nothing to forget: every request from an approver or
    administrator is checked, Django's own admin included.

    The session records which device was verified, not just that one was. An
    administrator who resets a colleague's authenticator therefore ends that
    colleague's verified sessions too, because the device they verified with no
    longer exists.
    """

    SESSION_KEY = "mfa_device"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.MFA_ENFORCED or not self._gated(request):
            return self.get_response(request)
        from django.shortcuts import redirect
        from django.urls import reverse

        request.session.pop(self.SESSION_KEY, None)
        target = "accounts:mfa_verify" if request.user.second_factor_enrolled else "accounts:mfa_enrol"
        url = reverse(target)
        if request.method == "GET" and request.path != reverse("accounts:dashboard"):
            from urllib.parse import urlencode

            url = f"{url}?{urlencode({'next': request.get_full_path()})}"
        return redirect(url)

    @classmethod
    def verified(cls, request) -> bool:
        device = getattr(request.user, "totp_device", None)
        return device is not None and device.confirmed and \
            request.session.get(cls.SESSION_KEY) == device.pk

    @classmethod
    def mark_verified(cls, request, device) -> None:
        request.session[cls.SESSION_KEY] = device.pk

    def _gated(self, request) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.requires_second_factor:
            return False
        if self.verified(request):
            return False
        return not self._exempt(request.path)

    @staticmethod
    def _exempt(path: str) -> bool:
        from django.urls import reverse

        exempt = (
            reverse("accounts:mfa_enrol"),
            reverse("accounts:mfa_verify"),
            reverse("accounts:logout"),
            settings.STATIC_URL,
            settings.MEDIA_URL,
        )
        return any(prefix and path.startswith(prefix) for prefix in exempt)
