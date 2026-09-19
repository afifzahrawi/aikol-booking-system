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
