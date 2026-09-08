"""Upload validation.

The rule is: images only, format sniffed rather than trusted, size capped, and
renamed on save (see `resource_image_path`). A filename and a Content-Type
header are both supplied by whoever is uploading and neither is evidence of
anything.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_image_upload(upload) -> None:
    """Refuse anything that is not a small JPEG, PNG or WebP.

    SVG is refused deliberately and by omission from the permitted list: it is a
    document format that can carry script, so serving a user-supplied SVG from
    the application's own origin would be a stored cross-site-scripting hole.
    """
    if upload.size > settings.MAX_UPLOAD_BYTES:
        limit = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError(
            f"That file is {upload.size / 1024 / 1024:.1f} MB. The limit is {limit} MB."
        )

    # Pillow reads the file's own header. This is the check that matters — the
    # extension and the browser's Content-Type are both attacker-controlled.
    try:
        from PIL import Image

        upload.seek(0)
        image = Image.open(upload)
        image.verify()
        fmt = (image.format or "").upper()
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 - any failure to parse is a refusal
        raise ValidationError("That file is not a readable image.") from exc
    finally:
        upload.seek(0)

    if fmt not in settings.PERMITTED_IMAGE_FORMATS:
        permitted = ", ".join(settings.PERMITTED_IMAGE_FORMATS)
        raise ValidationError(
            f"{fmt or 'That file'} is not a permitted format. Upload {permitted}."
        )
