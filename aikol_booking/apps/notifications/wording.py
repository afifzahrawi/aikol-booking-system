"""The wording of every email the system sends, and the office's edits to it.

Each email has a default subject and body written here, with fill-in fields in
braces: `{name}`, `{reference}` and so on. The office may replace the wording
from System, Emails; a replacement is a row in `EmailWording` and removing the
row restores the default. The code decides WHEN an email goes and WHAT the
fields contain; the office decides how it reads.

Fields are filled by a single pass over `{word}` patterns, never by
`str.format`. That matters twice over: `format` would let an edited template
reach attributes (`{user.password}`), and it would re-read braces inside a
value, so a purpose typed as "{reason}" would be expanded a second time. Here a
value is inserted exactly as it is, and an unknown `{word}` is left as written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FIELD = re.compile(r"\{([a-z_]+)\}")

BOOKING_FIELDS = {
    "name": "The name of the person the booking is for",
    "reference": "The booking reference, such as BK-202610-0004",
    "resource": "The room or car",
    "when": "The date and time, such as Friday, 02 October 2026, 15:00 to 17:00",
    "purpose": "What the booking is for",
    "details": "Reference, resource, time and purpose as a short list, with a line saying "
    "so when the office booked on the person's behalf",
}
SERIES_FIELDS = {
    "name": "The name of the person the weekly booking is for",
    "resource": "The room",
    "purpose": "What the weekly booking is for",
    "count": "How many dates",
    "dates": "Every date and time, one per line, with its reference",
}


@dataclass(frozen=True)
class EmailSpec:
    label: str
    sent_when: str
    subject: str
    body: str
    fields: dict = field(default_factory=dict)
    required: tuple = ()
    sample: dict = field(default_factory=dict)


SAMPLE_BOOKING = {
    "name": "Nurul Aisyah",
    "reference": "BK-202610-0004",
    "resource": "Seminar Room 1",
    "when": "Friday, 02 October 2026, 15:00 to 17:00",
    "purpose": "Moot court practice",
    "details": (
        "Reference: BK-202610-0004\n"
        "Resource:  Seminar Room 1\n"
        "When:      Friday, 02 October 2026, 15:00 to 17:00\n"
        "Purpose:   Moot court practice"
    ),
    "reason": "The room is needed for an examination that afternoon.",
    "driver": "Ahmad Faizal",
}
SAMPLE_SERIES = {
    "name": "Dr Sarah Lim",
    "resource": "Seminar Room 1",
    "purpose": "Contract Law tutorial",
    "count": "3",
    "dates": (
        "  Mon 05 Oct 2026, 10:00 to 12:00  BK-202610-0011\n"
        "  Mon 12 Oct 2026, 10:00 to 12:00  BK-202610-0012\n"
        "  Mon 26 Oct 2026, 10:00 to 12:00  BK-202610-0014"
    ),
    "not_included": (
        "Not included (1):\n  Mon 19 Oct 2026: semester break"
    ),
    "reason": "The room is closed for maintenance that week.",
}
SAMPLE_ACCOUNT = {
    "name": "Nurul Aisyah",
    "link": "https://aikol-booking.example/verify/Mw/abc123/",
    "days": "3",
}

EMAILS: dict[str, EmailSpec] = {
    "BOOKING_SUBMITTED": EmailSpec(
        label="Booking Request Received",
        sent_when="Someone asks for a room or car.",
        subject="Booking request received: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your booking request has been received and is waiting for a decision by the "
            "Kulliyyah office.\n\n"
            "{details}\n\n"
            "You will be emailed again once it is decided. Nobody else can book the same time "
            "while you wait.\n"
        ),
        fields=BOOKING_FIELDS,
        sample=SAMPLE_BOOKING,
    ),
    "BOOKING_APPROVED": EmailSpec(
        label="Room Booking Approved",
        sent_when="The office approves a room booking.",
        subject="Booking approved: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your booking has been approved.\n\n"
            "{details}\n\n"
            "Collect the key from the Kulliyyah office. If you can no longer use the booking, "
            "cancel it so that somebody else can.\n"
        ),
        fields=BOOKING_FIELDS,
        sample=SAMPLE_BOOKING,
    ),
    "BOOKING_APPROVED_VEHICLE": EmailSpec(
        label="Car Booking Approved, Waiting for Management",
        sent_when="The office approves a car booking. Kulliyyah management still has to decide.",
        subject="Booking approved: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your car booking has passed its first approval. Kulliyyah management must still "
            "approve the use of the car, and the office will assign a VMU driver.\n\n"
            "{details}\n\n"
            "You will be emailed again when the management decision is recorded.\n"
        ),
        fields=BOOKING_FIELDS,
        sample=SAMPLE_BOOKING,
    ),
    "VEHICLE_MANAGEMENT_APPROVED": EmailSpec(
        label="Car Use Approved by Management",
        sent_when="Kulliyyah management approves a car booking and a driver is assigned.",
        subject="Vehicle use approved: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Kulliyyah management has approved the use of the car and a VMU driver has been "
            "assigned. Your car booking is now fully approved.\n\n"
            "{details}\n\n"
            "Assigned driver: {driver}\n"
        ),
        fields={**BOOKING_FIELDS, "driver": "The name of the assigned VMU driver"},
        sample=SAMPLE_BOOKING,
    ),
    "VEHICLE_MANAGEMENT_REJECTED": EmailSpec(
        label="Car Use Not Approved by Management",
        sent_when="Kulliyyah management does not approve a car booking.",
        subject="Vehicle use not approved: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Kulliyyah management did not approve the use of the car. The booking is "
            "released.\n\n"
            "{details}\n\n"
            "Reason given: {reason}\n"
        ),
        fields={**BOOKING_FIELDS, "reason": "The reason management gave"},
        sample=SAMPLE_BOOKING,
    ),
    "BOOKING_REJECTED": EmailSpec(
        label="Booking Not Approved",
        sent_when="The office rejects a booking request.",
        subject="Booking not approved: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your booking request was not approved.\n\n"
            "{details}\n\n"
            "Reason given: {reason}\n\n"
            "You are welcome to ask for a different time.\n"
        ),
        fields={**BOOKING_FIELDS, "reason": "The reason the office gave"},
        required=("reason",),
        sample=SAMPLE_BOOKING,
    ),
    "BOOKING_CANCELLED": EmailSpec(
        label="Booking Cancelled",
        sent_when="A booking is cancelled, by the person or by the office.",
        subject="Booking cancelled: {reference}",
        body=(
            "Assalamualaikum {name},\n\n"
            "This booking has been cancelled.\n\n"
            "{details}\n\n"
            "Reason given: {reason}\n\n"
            "The time is now free for anyone else to book.\n"
        ),
        fields={**BOOKING_FIELDS, "reason": "The reason given for cancelling"},
        sample=SAMPLE_BOOKING,
    ),
    "SERIES_SUBMITTED": EmailSpec(
        label="Weekly Booking Request Received",
        sent_when="Someone asks for a weekly booking.",
        subject="Weekly booking request received: {resource}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your weekly booking request for {resource} has been received and is waiting for "
            "a decision by the Kulliyyah office.\n\n"
            "Purpose: {purpose}\n"
            "Dates requested: {count}\n\n"
            "{dates}\n\n"
            "{not_included}\n"
        ),
        fields={
            **SERIES_FIELDS,
            "not_included": "The dates left out and why, or nothing when every date was included",
        },
        required=("dates",),
        sample=SAMPLE_SERIES,
    ),
    "SERIES_APPROVED": EmailSpec(
        label="Weekly Booking Approved",
        sent_when="The office approves a weekly booking.",
        subject="Weekly booking approved: {resource}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your weekly booking for {resource} has been approved.\n\n"
            "Purpose: {purpose}\n"
            "Dates: {count}\n\n"
            "{dates}\n"
        ),
        fields=SERIES_FIELDS,
        required=("dates",),
        sample=SAMPLE_SERIES,
    ),
    "SERIES_REJECTED": EmailSpec(
        label="Weekly Booking Not Approved",
        sent_when="The office rejects a weekly booking.",
        subject="Weekly booking not approved: {resource}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Your weekly booking for {resource} was not approved.\n\n"
            "Purpose: {purpose}\n"
            "Dates: {count}\n\n"
            "{dates}\n\n"
            "Reason given: {reason}\n"
        ),
        fields={**SERIES_FIELDS, "reason": "The reason the office gave"},
        required=("reason",),
        sample=SAMPLE_SERIES,
    ),
    "SERIES_CANCELLED": EmailSpec(
        label="Weekly Booking Cancelled",
        sent_when="The future dates of a weekly booking are cancelled.",
        subject="Weekly booking cancelled: {resource}",
        body=(
            "Assalamualaikum {name},\n\n"
            "Future dates of your weekly booking for {resource} have been cancelled: {count} "
            "in all.\n\n"
            "{dates}\n\n"
            "Reason given: {reason}\n\n"
            "Dates that have already passed are not affected.\n"
        ),
        fields={**SERIES_FIELDS, "reason": "The reason given for cancelling"},
        sample=SAMPLE_SERIES,
    ),
    "ACCOUNT_VERIFY": EmailSpec(
        label="Confirm Your Email Address",
        sent_when="Someone registers, or changes their email address.",
        subject="Confirm your AIKOL Booking account",
        body=(
            "Assalamualaikum {name},\n\n"
            "Confirm this email address to start using the AIKOL Venue and Vehicle Booking "
            "System:\n\n"
            "{link}\n\n"
            "The link works for {days} days. Until you use it, you cannot make bookings.\n\n"
            "If you did not ask for this, you can ignore this email.\n"
        ),
        fields={
            "name": "The person's name",
            "link": "The confirmation link. Must stay in the email",
            "days": "How many days the link works",
        },
        required=("link",),
        sample=SAMPLE_ACCOUNT,
    ),
    "PASSWORD_RESET": EmailSpec(
        label="Reset Your Password",
        sent_when="Someone uses Forgotten your password?",
        subject="Reset your AIKOL Booking password",
        body=(
            "Assalamualaikum {name},\n\n"
            "Someone asked to reset the password for this address on the AIKOL Venue and "
            "Vehicle Booking System. Choose a new password here:\n\n"
            "{link}\n\n"
            "If you did not ask for this, ignore this email. Your password has not changed.\n"
        ),
        fields={
            "name": "The person's name",
            "link": "The reset link. Must stay in the email",
        },
        required=("link",),
        sample={**SAMPLE_ACCOUNT, "link": "https://aikol-booking.example/password-reset/Mw/abc123/"},
    ),
    "ACCOUNT_DUPLICATE_ATTEMPT": EmailSpec(
        label="Registration Tried With an Existing Address",
        sent_when="Someone registers with an address that already has an account.",
        subject="Somebody tried to register your AIKOL Booking address",
        body=(
            "Assalamualaikum {name},\n\n"
            "Somebody used this address on the registration form. You already have an account, "
            "so nothing was created and nothing has changed.\n\n"
            "If that was you, just sign in. If you have forgotten your password, use "
            "Forgotten your password? on the sign-in page.\n\n"
            "If it was not you, you can ignore this email.\n"
        ),
        fields={"name": "The person's name"},
        sample=SAMPLE_ACCOUNT,
    ),
    "ACCOUNT_IMPORTED": EmailSpec(
        label="Account Created by the Office",
        sent_when="The office adds people from a spreadsheet.",
        subject="An AIKOL Booking account has been created for you",
        body=(
            "Assalamualaikum {name},\n\n"
            "The Kulliyyah office has created an account for you on the AIKOL Venue and "
            "Vehicle Booking System.\n\n"
            "Set your password with Forgotten your password? on the sign-in page. Doing so also "
            "confirms this address, and then you can make bookings.\n"
        ),
        fields={"name": "The person's name"},
        sample=SAMPLE_ACCOUNT,
    ),
}


def fill(text: str, values: dict) -> str:
    """Insert each known field once. An unknown `{word}` is left as written."""

    def replace(match):
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return FIELD.sub(replace, text)


def problems(key: str, subject: str, body: str) -> list[str]:
    """What is wrong with an edited wording, in words the office can act on."""
    spec = EMAILS[key]
    used = set(FIELD.findall(subject)) | set(FIELD.findall(body))
    found = []
    unknown = sorted(used - set(spec.fields))
    if unknown:
        found.append(
            "This email cannot fill in "
            + ", ".join("{" + name + "}" for name in unknown)
            + ". Use only the fields listed beside the form."
        )
    missing = [name for name in spec.required if name not in used]
    if missing:
        found.append(
            "Keep "
            + ", ".join("{" + name + "}" for name in missing)
            + " in the email: without it the person cannot act on it."
        )
    return found


def wording(key: str) -> tuple[str, str]:
    """The subject and body in use: the office's edit if there is one."""
    from .models import EmailWording

    edited = EmailWording.objects.filter(key=key).first()
    spec = EMAILS[key]
    if edited:
        return edited.subject, edited.body
    return spec.subject, spec.body


def render(key: str, values: dict) -> tuple[str, str]:
    subject, body = wording(key)
    subject = " ".join(fill(subject, values).split())[:200]
    body = fill(body, values)
    # A field left empty (no dates were skipped, say) should not leave a stack
    # of blank lines behind it.
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    return subject, body


def send(key: str, *, to: str, values: dict, kind: str | None = None):
    from .services import queue_email

    subject, body = render(key, values)
    return queue_email(to=to, subject=subject, body=body, kind=kind or key)
