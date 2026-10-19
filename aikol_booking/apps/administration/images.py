"""Logo preparation: a transparent background at a sensible size.

Logos usually arrive as a JPEG or PNG on a white sheet. Shown on the tinted
header that sheet is a visible white box, and a 2,000-pixel original drawn 40
pixels high costs the first page most of a megabyte. Both are fixed once, when
the file is saved, rather than in CSS on every page.
"""

from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageChops, ImageFilter, ImageOps

# Drawn at most about 40 CSS pixels high; 160 covers a 3x phone screen with room.
LOGO_MAX_HEIGHT = 160
# A pixel this light (on its darkest channel) counts as the white sheet.
SHEET_LIGHTNESS = 238
# Edge pixels between this and the sheet are anti-aliasing and fade out.
EDGE_LIGHTNESS = 150


def transparent_logo(image: Image.Image) -> Image.Image:
    """Return the logo, resized, with its white made transparent.

    All white goes, not only the sheet around the mark: the holes inside
    letters (A, O, R) are white too, and left behind they show as white
    flecks on the tinted header. The header is light, so white detail inside
    the mark still reads as light once the header shows through it.
    """
    image = ImageOps.exif_transpose(image).convert("RGBA")
    if image.height > LOGO_MAX_HEIGHT:
        width = round(image.width * LOGO_MAX_HEIGHT / image.height)
        image = image.resize((width, LOGO_MAX_HEIGHT), Image.Resampling.LANCZOS)

    red, green, blue, alpha = image.split()
    lightness = ImageChops.darker(ImageChops.darker(red, green), blue)
    # Already-transparent pixels count as sheet too, so a logo that has some
    # transparency still has its white remainder removed.
    background = ImageChops.lighter(
        lightness.point(lambda v: 255 if v >= SHEET_LIGHTNESS else 0),
        ImageOps.invert(alpha).point(lambda v: 255 if v >= 250 else 0),
    )

    # Pixels touching the background fade with their lightness instead of
    # leaving a hard white halo.
    edge = ImageChops.subtract(background.filter(ImageFilter.MaxFilter(3)), background)
    span = 255 - EDGE_LIGHTNESS
    fade = lightness.point(
        lambda v: 255 if v <= EDGE_LIGHTNESS else max(0, round((255 - v) * 255 / span))
    )
    keep = ImageOps.invert(background)
    keep = ImageChops.composite(fade, keep, edge)
    image.putalpha(ImageChops.multiply(alpha, keep))
    return image


def logo_png(image: Image.Image) -> bytes:
    """A logo has few colours: a 256-colour PNG keeps the alpha at a fifth of the size."""
    buffer = BytesIO()
    image.quantize(256, method=Image.Quantize.FASTOCTREE).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def transparent_logo_upload(upload) -> ContentFile:
    """The uploaded logo as a transparent PNG, ready to assign to an ImageField."""
    upload.seek(0)
    with Image.open(upload) as source:
        logo = transparent_logo(source)
    return ContentFile(logo_png(logo), name=f"{Path(upload.name).stem}.png")
