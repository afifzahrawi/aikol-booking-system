"""Secret-free settings used only to collect static assets in the image build."""

from .base import *  # noqa: F401,F403


SECRET_KEY = "image-build-only-not-used-at-runtime"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
