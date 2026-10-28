"""Small security headers that are not provided by Django's middleware."""

from urllib.parse import urlsplit

from django.conf import settings


class SecurityPolicyMiddleware:
    """Apply a deny-by-default browser policy to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # A back-button history entry must never reveal a signed-in person's
        # booking or contact details after they sign out. Browser back/forward
        # caches can bypass a new request entirely unless dynamic authenticated
        # responses explicitly opt out.
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            response.headers.setdefault("Cache-Control", "no-store, max-age=0, private")
            response.headers.setdefault("Pragma", "no-cache")
        media_origin = getattr(settings, "MEDIA_URL", "")
        image_sources = ["'self'", "data:"]
        if media_origin.startswith("https://"):
            parsed_media = urlsplit(media_origin)
            image_sources.append(f"{parsed_media.scheme}://{parsed_media.netloc}")
        directives = [
            "default-src 'self'",
            "base-uri 'self'",
            "connect-src 'self'",
            "font-src 'self'",
            f"img-src {' '.join(image_sources)}",
            "object-src 'none'",
            # Allows only the inline speculation-rules block in base.html, never
            # inline script: it is JSON the browser reads, not code it runs.
            "script-src 'self' 'inline-speculation-rules'",
            "style-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        # Only where the page itself arrived over TLS. Sent on a plain-HTTP
        # development server it rewrites the browser's own requests to https,
        # which nothing is listening for: a form posts, the server acts, and
        # the redirect the browser follows dies with "Failed to fetch". The
        # action has happened and the screen says it has not.
        if request.is_secure():
            directives.append("upgrade-insecure-requests")
        response.headers.setdefault("Content-Security-Policy", "; ".join(directives))
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


class KioskLockMiddleware:
    """A session turned into the office key kiosk reaches the kiosk and nothing else.

    The kiosk runs signed in as an Admin, because the office wanted no extra
    account to look after. The PC stands where anyone can use it, so the
    session is locked here, for every URL, rather than by hiding links: typing
    an address into the bar must not reach the Admin's screens. Leaving needs
    the Admin's password (`bookings:kiosk_exit`).
    """

    SESSION_KEY = "kiosk_mode"
    ALLOWED_PREFIXES = ("/kiosk/", "/static/", "/media/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session = getattr(request, "session", None)
        if session is not None and session.get(self.SESSION_KEY):
            from django.shortcuts import redirect
            from django.urls import reverse

            allowed = request.path.startswith(self.ALLOWED_PREFIXES) or request.path in {
                reverse("accounts:logout"),
                reverse("accounts:login"),
            }
            if not allowed:
                return redirect("bookings:kiosk")
        return self.get_response(request)


class SlidingSessionMiddleware:
    """Keeps a signed-in session alive while it is used, without a database
    write on every click.

    `SESSION_SAVE_EVERY_REQUEST` wrote the session back after every page: three
    round trips to the database on each click, for an expiry that only needs
    to move forward now and then. Touching the session at most every
    `REFRESH_SECONDS` keeps the 12-hour idle limit to within ten minutes.
    """

    REFRESH_SECONDS = 600
    KEY = "_refreshed_at"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = getattr(request, "session", None)
        if session is not None and not session.is_empty():
            import time

            now = int(time.time())
            if now - int(session.get(self.KEY, 0)) >= self.REFRESH_SECONDS:
                session[self.KEY] = now  # marks the session modified, so it is saved
        return response
