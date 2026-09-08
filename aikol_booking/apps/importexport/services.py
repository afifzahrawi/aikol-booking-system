"""CSV import: parse, validate, preview, then insert.

Nothing is written until an administrator has seen the errors and confirmed. The
preview is generated entirely from validation results, so what they approve is
exactly what happens.

Every failing row is reported with its line number and EVERY reason it failed,
not just the first — an administrator should be able to correct the spreadsheet
in one pass rather than discovering the next problem on the next upload.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.resources.models import Facility, Resource, ResourceStatus, Vehicle, Venue

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass
class RowResult:
    line: int
    data: dict
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ImportPlan:
    kind: str
    rows: list[RowResult] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> list[RowResult]:
        return [r for r in self.rows if r.ok]

    @property
    def invalid(self) -> list[RowResult]:
        return [r for r in self.rows if not r.ok]

    @property
    def usable(self) -> bool:
        return not self.file_errors and bool(self.valid)


# --------------------------------------------------------------- templates

TEMPLATES: dict[str, list[str]] = {
    "facilities": ["code", "name", "applies_to", "status"],
    "users": ["name", "email", "identification_number", "phone", "affiliation", "role", "status"],
    "venues": [
        "code", "name", "building", "floor", "venue_type", "capacity", "facilities",
        "bookable_window_start", "bookable_window_end",
    ],
    "vehicles": [
        "code", "name", "registration_number", "vehicle_class", "make", "model", "year",
        "seats", "transmission", "fuel_type", "facilities", "road_tax_expiry",
    ],
}

VENUE_TYPES = {label.lower(): value for value, label in Venue.VenueType.choices}
AFFILIATIONS = {label.lower(): value for value, label in Affiliation.choices}
ROLES = {label.lower(): value for value, label in Role.choices}


def read_rows(upload) -> tuple[list[dict], list[str], list[str]]:
    """Parse the upload into dictionaries, streaming rather than slurping.

    Returns (rows, header, file-level errors). A file-level error means nothing
    can be validated at all — a missing column, say — so the caller stops.
    """
    if upload.size > MAX_UPLOAD_BYTES:
        return [], [], [f"The file is {upload.size / 1024 / 1024:.1f} MB. The limit is 10 MB."]

    wrapper = io.TextIOWrapper(upload.file, encoding="utf-8-sig", errors="replace")
    reader = csv.reader(wrapper)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        return [], [], ["The file is empty."]

    rows = []
    for line, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue  # a blank line is not an error
        rows.append({"__line__": line, "__values__": values, "__header__": header})
    return rows, header, []


def validate(kind: str, upload) -> ImportPlan:
    plan = ImportPlan(kind=kind)
    expected = TEMPLATES[kind]
    raw, header, file_errors = read_rows(upload)
    plan.file_errors = list(file_errors)
    if plan.file_errors:
        return plan

    missing = [column for column in expected if column not in header]
    if missing:
        # The whole file is rejected outright: validating rows against a header
        # we do not understand would produce misleading per-row errors.
        plan.file_errors.append(
            "The file is missing required column"
            + ("s" if len(missing) > 1 else "")
            + ": "
            + ", ".join(missing)
            + f". Expected: {', '.join(expected)}."
        )
        return plan

    validator = {
        "facilities": _validate_facility,
        "users": _validate_user,
        "venues": _validate_venue,
        "vehicles": _validate_vehicle,
    }[kind]

    seen: dict[str, set] = {}
    for entry in raw:
        values, line = entry["__values__"], entry["__line__"]
        result = RowResult(line=line, data={})
        if len(values) != len(header):
            result.errors.append(
                f"This row has {len(values)} value(s); the header has {len(header)}."
            )
            plan.rows.append(result)
            continue
        result.data = {header[i]: values[i].strip() for i in range(len(header))}
        validator(result, seen)
        plan.rows.append(result)
    return plan


def _unique_in_file(result: RowResult, seen: dict, key: str, value: str, label: str) -> None:
    """Duplicates WITHIN the file, which the database cannot catch."""
    if not value:
        return
    bucket = seen.setdefault(key, set())
    lowered = value.lower()
    if lowered in bucket:
        result.errors.append(f"{label} '{value}' appears more than once in this file.")
    bucket.add(lowered)


def _facility_codes(result: RowResult, raw: str, applies: tuple[str, ...]) -> list[str]:
    """Pipe-separated CODES, not display names.

    An unknown code is a row error, never a silent creation: a typo in a
    spreadsheet must not quietly add "projecter" to the facility list for
    everyone who books afterwards.
    """
    if not raw:
        return []
    codes = [c.strip() for c in raw.split("|") if c.strip()]
    known = dict(
        Facility.objects.filter(code__in=codes).values_list("code", "applies_to")
    )
    valid = []
    for code in codes:
        if code not in known:
            result.errors.append(
                f"Facility code '{code}' does not exist. Import the facilities first."
            )
        elif known[code] not in applies:
            result.errors.append(f"Facility '{code}' does not apply to this kind of resource.")
        else:
            valid.append(code)
    return valid


def _positive_int(result: RowResult, raw: str, label: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        result.errors.append(f"{label} must be a whole number.")
        return None
    if value <= 0:
        result.errors.append(f"{label} must be greater than zero.")
        return None
    return value


def _time(result: RowResult, raw: str, label: str) -> dt.time | None:
    if not raw:
        return None
    try:
        hour, minute = raw.split(":")
        return dt.time(int(hour), int(minute))
    except (ValueError, TypeError):
        result.errors.append(f"{label} must be a time as HH:MM.")
        return None


# ------------------------------------------------------------- validators


def _validate_facility(result: RowResult, seen: dict) -> None:
    data = result.data
    code = data.get("code", "").lower()
    if not code:
        result.errors.append("code is required.")
    elif not code.replace("_", "").replace("-", "").isalnum():
        result.errors.append("code must be lower-case letters, digits, hyphen or underscore.")
    _unique_in_file(result, seen, "code", code, "Facility code")
    if not data.get("name"):
        result.errors.append("name is required.")

    applies = data.get("applies_to", "").strip().lower()
    mapping = {"venue": "VENUE", "venues": "VENUE", "vehicle": "VEHICLE",
               "vehicles": "VEHICLE", "both": "BOTH"}
    if applies not in mapping:
        result.errors.append("applies_to must be Venue, Vehicle or Both.")
    else:
        result.data["_applies_to"] = mapping[applies]

    status = data.get("status", "").strip().lower()
    if status not in ("active", "inactive", ""):
        result.errors.append("status must be Active or Inactive.")
    result.data["_is_active"] = status != "inactive"
    result.data["_code"] = code

    # This is the ONE template where re-importing an existing code updates
    # rather than fails: a facility list is maintained, not loaded once, and the
    # code is the stable identity resources are already linked to.
    if Facility.objects.filter(code=code).exists():
        result.warnings.append(f"'{code}' already exists and will be updated, not created.")


def _validate_user(result: RowResult, seen: dict) -> None:
    data = result.data
    if not data.get("name"):
        result.errors.append("name is required.")

    email = data.get("email", "").lower()
    if not email:
        result.errors.append("email is required.")
    else:
        try:
            validate_email(email)
        except ValidationError:
            result.errors.append(f"'{email}' is not a valid email address.")
        else:
            domain = email.rsplit("@", 1)[-1]
            if domain not in settings.IIUM_EMAIL_DOMAINS:
                result.errors.append(
                    f"'{email}' is not an IIUM address. Bulk import is for IIUM accounts; "
                    "a member of the public registers themselves."
                )
            if User.objects.filter(email__iexact=email).exists():
                result.errors.append(f"An account already exists for '{email}'.")
    _unique_in_file(result, seen, "email", email, "Email")

    number = data.get("identification_number", "")
    if not number:
        result.errors.append("identification_number is required (decision 18).")
    elif User.objects.filter(identification_number__iexact=number).exists():
        result.errors.append(f"'{number}' is already registered.")
    _unique_in_file(result, seen, "number", number, "Matriculation or staff number")

    if not data.get("phone"):
        result.errors.append("phone is required (decision 18).")

    affiliation = data.get("affiliation", "").strip().lower()
    if affiliation not in AFFILIATIONS or AFFILIATIONS[affiliation] == Affiliation.PUBLIC:
        result.errors.append("affiliation must be Student, Lecturer or Staff.")
    else:
        result.data["_affiliation"] = AFFILIATIONS[affiliation]

    role = data.get("role", "").strip().lower() or "user"
    if role not in ROLES:
        result.errors.append("role must be User, Approver or Administrator.")
    else:
        result.data["_role"] = ROLES[role]

    status = data.get("status", "").strip().lower()
    if status not in ("active", "inactive", ""):
        result.errors.append("status must be Active or Inactive.")
    result.data["_is_active"] = status != "inactive"


def _validate_resource_code(result: RowResult, seen: dict, code: str) -> None:
    """Venues and vehicles share one `resources.code` namespace, so a venue
    cannot take a code a vehicle already holds."""
    if not code:
        result.errors.append("code is required.")
        return
    _unique_in_file(result, seen, "code", code, "Resource code")
    if Resource.objects.filter(code__iexact=code).exists():
        result.errors.append(
            f"Resource code '{code}' is already in use. Venues and vehicles share one namespace."
        )


def _validate_venue(result: RowResult, seen: dict) -> None:
    data = result.data
    _validate_resource_code(result, seen, data.get("code", ""))
    if not data.get("name"):
        result.errors.append("name is required.")

    venue_type = data.get("venue_type", "").strip().lower()
    if venue_type not in VENUE_TYPES:
        result.errors.append(
            "venue_type must be one of: " + ", ".join(sorted(VENUE_TYPES))
        )
    else:
        result.data["_venue_type"] = VENUE_TYPES[venue_type]

    result.data["_capacity"] = _positive_int(result, data.get("capacity", ""), "capacity")

    opens = _time(result, data.get("bookable_window_start", ""), "bookable_window_start")
    closes = _time(result, data.get("bookable_window_end", ""), "bookable_window_end")
    if opens and closes and closes <= opens:
        result.errors.append("bookable_window_end must be after bookable_window_start.")
    # Blank inherits the confirmed 08:00-22:00 window (decision 9).
    result.data["_opens_at"] = opens or dt.time(8, 0)
    result.data["_closes_at"] = closes or dt.time(22, 0)

    result.data["_facilities"] = _facility_codes(
        result, data.get("facilities", ""), ("VENUE", "BOTH")
    )


def _validate_vehicle(result: RowResult, seen: dict) -> None:
    data = result.data
    _validate_resource_code(result, seen, data.get("code", ""))
    if not data.get("name"):
        result.errors.append("name is required.")

    registration = data.get("registration_number", "")
    if not registration:
        result.errors.append("registration_number is required.")
    elif Vehicle.objects.filter(registration_number__iexact=registration).exists():
        result.errors.append(f"Registration '{registration}' is already recorded.")
    _unique_in_file(result, seen, "registration", registration, "Registration")

    vehicle_class = data.get("vehicle_class", "").strip().lower() or "car"
    if vehicle_class != "car":
        result.errors.append(
            "vehicle_class must be Car. Other classes are rejected until they are supported."
        )

    result.data["_seats"] = _positive_int(result, data.get("seats", ""), "seats")
    result.data["_year"] = _positive_int(result, data.get("year", ""), "year")

    transmission = data.get("transmission", "").strip().lower()
    if transmission not in ("auto", "automatic", "manual", ""):
        result.errors.append("transmission must be Auto or Manual.")
    result.data["_transmission"] = "MANUAL" if transmission == "manual" else "AUTO"

    raw_expiry = data.get("road_tax_expiry", "")
    try:
        expiry = dt.date.fromisoformat(raw_expiry)
    except ValueError:
        result.errors.append("road_tax_expiry must be a date as YYYY-MM-DD.")
        expiry = None
    else:
        # A past date is a WARNING, not an error. An administrator may be
        # loading a fleet mid-renewal, and refusing the whole import would be
        # unhelpful; the car simply cannot be booked until the date is updated.
        if expiry < timezone.localdate():
            result.warnings.append(
                f"Road tax expired on {expiry:%d %b %Y}. The vehicle is imported but "
                "cannot be booked until the date is updated."
            )
    result.data["_road_tax_expiry"] = expiry

    result.data["_facilities"] = _facility_codes(
        result, data.get("facilities", ""), ("VEHICLE", "BOTH")
    )


# ----------------------------------------------------------------- import


@transaction.atomic
def apply_plan(plan: ImportPlan) -> dict:
    """One transaction for the whole import: if any statement fails, nothing is
    written. Valid rows may be imported while invalid ones are skipped, but only
    once the administrator has seen the error list and confirmed."""
    handler = {
        "facilities": _import_facilities,
        "users": _import_users,
        "venues": _import_venues,
        "vehicles": _import_vehicles,
    }[plan.kind]
    created, updated = handler(plan.valid)
    return {
        "created": created,
        "updated": updated,
        "skipped": len(plan.invalid),
        "kind": plan.kind,
    }


def _import_facilities(rows: list[RowResult]) -> tuple[int, int]:
    created = updated = 0
    last = Facility.objects.order_by("-display_order").first()
    order = (last.display_order if last else 0) + 1
    for row in rows:
        facility, made = Facility.objects.update_or_create(
            code=row.data["_code"],
            defaults={
                "name": row.data["name"],
                "applies_to": row.data["_applies_to"],
                "is_active": row.data["_is_active"],
            },
        )
        if made:
            facility.display_order = order
            facility.save(update_fields=["display_order"])
            order += 1
            created += 1
        else:
            updated += 1
    return created, updated


def _import_users(rows: list[RowResult]) -> tuple[int, int]:
    """Imported accounts are unverified and have no usable password.

    Setting one through the activation link verifies the address, so an imported
    user follows the same proof-of-mailbox path as somebody who registered
    themselves. There is no password column in the template for the same reason.
    """
    from apps.notifications.services import queue_email

    people = []
    for row in rows:
        person = User(
            full_name=row.data["name"],
            email=row.data["email"].lower(),
            identification_number=row.data["identification_number"],
            phone=row.data["phone"],
            affiliation=row.data["_affiliation"],
            role=row.data["_role"],
            is_active=row.data["_is_active"],
            email_verified=False,
        )
        person.set_unusable_password()
        people.append(person)
    User.objects.bulk_create(people, batch_size=500)

    for person in people:
        queue_email(
            to=person.email,
            subject="An AIKOL Booking account has been created for you",
            body=(
                f"Assalamualaikum {person.full_name},\n\n"
                "The Kulliyyah office has created an account for you on the AIKOL Room and "
                "Vehicle Booking System.\n\n"
                "Set your password using the 'Forgotten your password?' link on the sign-in "
                "page. Doing so also confirms this address, after which you can make bookings.\n"
            ),
            kind="ACCOUNT_IMPORTED",
        )
    return len(people), 0


def _bulk_resources(rows: list[RowResult], child_model, build_child) -> tuple[int, int]:
    """`bulk_create` and multi-table inheritance do not mix.

    Django refuses `bulk_create` on a child model outright — not merely when the
    parent is missing, but always: `Can't bulk create a multi-table inherited
    model`. So the parent `Resource` rows go in through the ORM as one
    statement, and the child rows go in as one `executemany` against the child
    table directly, using the primary keys the parent insert returned.

    Raw SQL for the second half is deliberate and narrow. It touches one table,
    with column names taken from the model's own `_meta`, inside the caller's
    transaction — the alternative is one INSERT per row, which is precisely what
    a bulk import exists to avoid.
    """
    from django.db import connection

    resource_type = "VENUE" if child_model is Venue else "VEHICLE"
    parents = [
        Resource(
            code=row.data["code"],
            name=row.data["name"],
            resource_type=resource_type,
            status=ResourceStatus.ACTIVE,
        )
        for row in rows
    ]
    Resource.objects.bulk_create(parents, batch_size=500)

    children = [build_child(row, parent) for row, parent in zip(rows, parents)]
    if children:
        local = [f for f in child_model._meta.local_fields]
        columns = [f.column for f in local]
        table = child_model._meta.db_table
        quote = connection.ops.quote_name
        placeholders = ", ".join(["%s"] * len(columns))
        sql = (
            f"INSERT INTO {quote(table)} "
            f"({', '.join(quote(c) for c in columns)}) VALUES ({placeholders})"
        )
        values = [
            [f.get_db_prep_save(f.pre_save(child, True), connection) for f in local]
            for child in children
        ]
        with connection.cursor() as cursor:
            cursor.executemany(sql, values)

    # Facilities go through the explicit join, which carries the unique
    # constraint.
    from apps.resources.models import ResourceFacility

    codes = {c for row in rows for c in row.data["_facilities"]}
    ids = dict(Facility.objects.filter(code__in=codes).values_list("code", "pk"))
    links = [
        ResourceFacility(resource_id=parent.pk, facility_id=ids[code])
        for row, parent in zip(rows, parents)
        for code in row.data["_facilities"]
    ]
    ResourceFacility.objects.bulk_create(links, batch_size=500, ignore_conflicts=True)
    return len(parents), 0


def _import_venues(rows: list[RowResult]) -> tuple[int, int]:
    def build(row, parent):
        return Venue(
            resource_ptr_id=parent.pk,
            venue_type=row.data["_venue_type"],
            location=row.data.get("building", ""),
            floor=row.data.get("floor", ""),
            capacity=row.data["_capacity"],
            opens_at=row.data["_opens_at"],
            closes_at=row.data["_closes_at"],
        )

    return _bulk_resources(rows, Venue, build)


def _import_vehicles(rows: list[RowResult]) -> tuple[int, int]:
    def build(row, parent):
        return Vehicle(
            resource_ptr_id=parent.pk,
            registration_number=row.data["registration_number"],
            vehicle_class="CAR",
            make=row.data.get("make", ""),
            model=row.data.get("model", ""),
            year=row.data["_year"],
            seats=row.data["_seats"],
            transmission=row.data["_transmission"],
            fuel_type=row.data.get("fuel_type", ""),
            road_tax_expiry=row.data["_road_tax_expiry"],
        )

    return _bulk_resources(rows, Vehicle, build)
