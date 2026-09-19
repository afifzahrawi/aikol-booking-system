"""Time-based one-time passwords, RFC 6238, on the standard library.

Administrators and approvers must present a second factor (`docs/technical/
security.md`, "Phishing resistance"). An authenticator application was chosen
over passkeys for the first release because it works on any phone the office
already owns, needs no JavaScript, and has an obvious recovery path; passkeys
can be layered on later without undoing any of this.

The algorithm is thirty lines, so it is implemented here rather than imported:
one fewer dependency to review, and the test file carries the RFC's own test
vectors so the implementation is checked against the standard, not against
itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
#: Accept the previous and next step as well as the current one, for clocks a
#: little out and a person who reads the code just as it rolls over.
WINDOW = 1

RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i


def generate_secret() -> str:
    """A fresh 160-bit secret, base32 without padding, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


def hotp(secret: str, counter: int, digits: int = DIGITS) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def current_step(at: float | None = None) -> int:
    return int((time.time() if at is None else at) // STEP_SECONDS)


def totp(secret: str, at: float | None = None, digits: int = DIGITS) -> str:
    return hotp(secret, current_step(at), digits)


def verify(secret: str, code: str, *, at: float | None = None,
           after_step: int = 0) -> int | None:
    """The step the code matched, or None.

    `after_step` is the last step already accepted for this device. A code is
    good for one use: an attacker who shoulder-surfs a code and types it
    within the same thirty seconds gets nothing, because the genuine sign-in
    already consumed that step.
    """
    candidate = "".join(ch for ch in code if ch.isdigit())
    if len(candidate) != DIGITS:
        return None
    now = current_step(at)
    for step in range(now - WINDOW, now + WINDOW + 1):
        if step <= after_step:
            continue
        if hmac.compare_digest(hotp(secret, step), candidate):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """What the QR code encodes, per the otpauth convention every app reads."""
    label = quote(f"{issuer}:{account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def grouped(secret: str) -> str:
    """The secret in blocks of four, for typing in by hand when the camera fails."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)).lower()


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Ten codes of the form `abcd2-efgh3`. Shown once, stored hashed."""
    def one() -> str:
        chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{chars[:5]}-{chars[5:]}"
    return [one() for _ in range(count)]


def normalise_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def qr_svg(uri: str) -> str:
    """The provisioning URI as an inline SVG. Rendered server-side and sent as
    markup, so the CSP's `img-src` needs no exception and nothing about the
    secret leaves in a URL."""
    import qrcode
    from qrcode.image.svg import SvgPathImage

    image = qrcode.make(uri, image_factory=SvgPathImage, box_size=10, border=2)
    return image.to_string(encoding="unicode")
