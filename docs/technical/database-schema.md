# Database schema

Target: PostgreSQL in production, SQLite in development. All access through the Django ORM.

All values here reflect the decisions confirmed by AIKOL — see section 5 of `CLAUDE.md`. They are
settled, not proposals.

## Shape of the design

The system books two kinds of thing: **venues** and **vehicles**. They differ in their attributes
and in almost nothing else. Both are reserved for a period, both require approval, both have keys
issued and returned, and neither may ever be double-booked.

So there is one `resources` table carrying everything they share, and `venues` and `vehicles` extend
it with their own attributes. `bookings.resource_id` points at `resources`. This is Django's
multi-table inheritance: `class Venue(Resource)` and `class Vehicle(Resource)`.

The reason is not tidiness. The system's core promise is that overlapping bookings are impossible,
and that promise is kept by one application rule plus one database constraint. A separate
`vehicle_bookings` table would need its own copy of both, its own conflict tests, and its own
availability query — two implementations of the same guarantee, free to drift apart. One table means
a bug fixed in the conflict rule is fixed for cars and moot courts at the same moment.

```
  facilities  ◄───  resource_facilities  ───►  resources
  (code, name,          (M2M join)              (code, name, type, status,
   applies_to)                                   approval, rules, window)
                                                      │
                                          ┌───────────┴───────────┐
                                          ▼                       ▼
                                       venues                  vehicles
                                  (capacity, building,   (registration, make,
                                   floor, venue_type)     seats, road tax)
                                          └───────────┬───────────┘
                                                      ▼
                                                   bookings  ──►  booking_series
                                                      │
                                          ┌───────────┴───────────┐
                                          ▼                       ▼
                                    key_handovers            email_outbox
```

## Tables

### `users`
Custom user model (`accounts.User`), extending `AbstractBaseUser` so `email` is the login field.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `name` | varchar(150) | Full name as displayed |
| `email` | varchar(254) | **Unique.** Login identifier. Must end `@iium.edu.my` or `@live.iium.edu.my` |
| `password` | varchar(128) | Django password hash (PBKDF2 / Argon2). Never plain text |
| `identification_number` | varchar(20) | **Unique.** Matriculation or staff number. Collected for documentation (decision 18). **Not** a login credential |
| `phone` | varchar(20) | Decision 18 |
| `affiliation` | varchar(10) | `STUDENT`, `LECTURER`, `STAFF` — who the person is |
| `role` | varchar(15) | `USER`, `APPROVER`, `ADMINISTRATOR` — what the person may do |
| `status` | varchar(10) | `ACTIVE`, `INACTIVE`. Deactivation replaces deletion |
| `email_verified` | bool | False until the registration link is followed. An unverified account cannot book |
| `driving_licence_number` | varchar(30), null | Required before a vehicle booking, not at registration |
| `driving_licence_expiry` | date, null | Validated against the trip end date |
| `is_staff`, `is_superuser` | bool | Django admin access; distinct from `role` |
| `created_at`, `updated_at` | timestamptz | |

**Affiliation and role are separate fields, deliberately.** Decision 5 requires an Approver who is
not a full administrator, and the follow-up decision restricts vehicle booking to lecturers and
staff. A single `role` column cannot express "a lecturer who is also an approver" without either
losing the affiliation that governs vehicle eligibility or inventing combined values. Two orthogonal
fields cost one extra column and remove the whole problem.

Vehicle eligibility is therefore `affiliation in (LECTURER, STAFF)`, and approval rights are
`role in (APPROVER, ADMINISTRATOR)`. Neither is inferred from the other.

Users are **never deleted** while bookings reference them. `on_delete=PROTECT` enforces this.

### `resources`
Everything a venue and a vehicle have in common.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `code` | varchar(30) | **Unique.** Stable key for CSV import — `AIKOL-MC-01`, `AIKOL-CAR-01` |
| `resource_type` | varchar(10) | `VENUE`, `VEHICLE`. Denormalised from the subclass so lists can filter without a join |
| `name` | varchar(150) | |
| `description` | text | |
| `status` | varchar(20) | `ACTIVE`, `MAINTENANCE`, `INACTIVE` |
| `approval_required` | bool, default true | Decision 4: true for every resource in the first release. The field stays because AIKOL may relax the rule |
| `booking_restrictions` | text | Free text shown to users |
| `rules` | text | Displayed on the resource page |
| `bookable_window_start`, `bookable_window_end` | time, null | Per-resource override; null falls back to the 08:00–22:00 system setting (decision 9) |
| `created_at`, `updated_at` | timestamptz | |

### `facilities`
Administrators create and maintain this list themselves; it is not fixed in code.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `code` | varchar(40) | **Unique.** Slug used by CSV import. Generated from the name, then immutable |
| `name` | varchar(80) | Display label. Editable — renaming "Smart TV" to "Smart Television" must not break existing links |
| `applies_to` | varchar(10) | `VENUE`, `VEHICLE`, `BOTH`. Controls which options the resource form offers |
| `display_order` | integer | Ordering on venue pages and filter lists |
| `status` | varchar(10) | `ACTIVE`, `INACTIVE` |
| `created_at`, `updated_at` | timestamptz | |

A facility in use is **deactivated, never deleted**, in line with the rule applied everywhere else in
this schema. Deactivating hides it from the resource form and from filters while leaving the
resources that already have it untouched. Deletion is permitted only when no resource references it.

`code` and `name` are separate on purpose. The code is what a CSV import and a saved filter URL
refer to; the name is what an administrator edits. Letting the display name double as the key would
mean a typo correction silently orphaned every import template.

### `resource_facilities`
The many-to-many join. In Django this is a `ManyToManyField` on `Resource` with an explicit through
model, so it can carry its own timestamps.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `resource_id` | FK → resources | `on_delete=CASCADE` |
| `facility_id` | FK → facilities | `on_delete=PROTECT` — a facility in use cannot be deleted out from under a resource |
| `created_at` | timestamptz | |

Unique together on `(resource_id, facility_id)`.

The join sits on `resources`, not on `venues`, so a vehicle can carry features such as GPS or a
dashcam without a parallel `vehicle_features` table appearing later. `applies_to` keeps the venue
form from offering "Dashcam" and the vehicle form from offering "Whiteboard".

### `venues`
Primary key is also the foreign key to `resources` (Django MTI).

| Field | Type | Notes |
| --- | --- | --- |
| `resource_ptr_id` | bigint PK / FK → resources | |
| `building`, `floor`, `location` | varchar | `location` is the display string |
| `capacity` | integer | Validates `attendee_count` |
| `venue_type` | varchar(50) | Moot Court, Seminar Room, … |

### `vehicles`

| Field | Type | Notes |
| --- | --- | --- |
| `resource_ptr_id` | bigint PK / FK → resources | |
| `registration_number` | varchar(15) | **Unique.** Number plate |
| `vehicle_class` | varchar(20) | `CAR` is the only value in the first release. The column exists so vans or buses do not require a migration of meaning |
| `make`, `model` | varchar(50) | |
| `year` | integer | |
| `seats` | integer | Validates `passenger_count` |
| `transmission` | varchar(10) | `AUTO`, `MANUAL` — a requester who cannot drive manual needs to know before booking |
| `fuel_type` | varchar(20) | |
| `road_tax_expiry`, `insurance_expiry` | date | A trip ending after either date is refused; both are shown on the admin list |
| `current_mileage` | integer | Updated from the last key return |

### `resource_images`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `resource_id` | FK → resources | `on_delete=CASCADE` |
| `image_path` | varchar | Relative to `MEDIA_ROOT` |
| `display_order` | integer | 0 = main image |
| `created_at` | timestamptz | |

### `booking_series`
The recurrence definition (decision 15). It is a template only — it never reserves anything itself.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `resource_id` | FK → resources | `on_delete=PROTECT` |
| `user_id`, `created_by_id` | FK → users | `on_delete=PROTECT` |
| `frequency` | varchar(10) | `WEEKLY` in the first release; `DAILY`, `MONTHLY` reserved |
| `interval` | integer, default 1 | Every N weeks |
| `weekdays` | JSON | e.g. `[1, 3]` for Monday and Wednesday |
| `series_start_date`, `series_end_date` | date | Typically a semester |
| `start_time`, `end_time` | time | Applied to every occurrence |
| `purpose` | text | Copied to each occurrence |
| `created_at` | timestamptz | |

**Every occurrence is a real row in `bookings`** carrying `series_id`. Occurrences are never computed
on the fly at read time. A booking that does not exist as a row cannot be covered by the exclusion
constraint, so a virtual occurrence would be invisible to the one mechanism that makes double
booking impossible.

### `bookings`
The central table. Expected to grow to hundreds of thousands of rows.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `booking_reference` | varchar(20) | **Unique.** Format `BK-YYYYMM-NNNN` |
| `user_id` | FK → users | `on_delete=PROTECT`. The person the booking is *for* |
| `created_by_id` | FK → users | `on_delete=PROTECT`. Who submitted it. Differs from `user_id` when an administrator books on someone's behalf (decision 14) |
| `resource_id` | FK → resources | `on_delete=PROTECT` |
| `series_id` | FK → booking_series, null | `on_delete=SET_NULL`. Null for one-off bookings |
| `start_at`, `end_at` | timestamptz | `end_at > start_at` enforced by a check constraint |
| `purpose` | text | The "remarks / purpose" of decision 18 |
| `attendee_count` | integer, null | **Venues only.** Validated against `venue.capacity` |
| `origin` | varchar(200), null | **Vehicles only.** Where the car leaves from |
| `destination` | varchar(200), null | **Vehicles only.** Where the car is going |
| `passenger_count` | integer, null | **Vehicles only.** Validated against `vehicle.seats` |
| `driver_arrangement` | varchar(10), null | **Vehicles only.** `SELF` or `VMU`. `SELF` requires `affiliation in (LECTURER, STAFF)` |
| `driver_name` | varchar(150), null | **Vehicles only.** Who will actually drive |
| `driver_contact` | varchar(30), null | **Vehicles only.** Telephone number for the driver |
| `driver_staff_no` | varchar(20), null | **Vehicles only.** The driver's staff number |
| `vmu_reference` | varchar(40), null | **Vehicles only.** The STADD request reference, once the Vehicle Management Unit issues one |
| `management_approved_at` | timestamptz, null | **VMU bookings only.** Kulliyyah management approval to use the car — separate from, and additional to, the booking approval |
| `management_approved_by_id` | FK → users, null | `on_delete=SET_NULL` |
| `status` | varchar(12) | `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`, `COMPLETED` |
| `rejection_reason` | text | Required when status becomes `REJECTED` |
| `cancellation_reason` | text | **Required** for every cancellation, by anyone (confirmed follow-up decision) |
| `approved_by_id` | FK → users, null | `on_delete=SET_NULL` |
| `cancelled_by_id` | FK → users, null | `on_delete=SET_NULL` |
| `approved_at`, `cancelled_at` | timestamptz, null | |
| `created_at`, `updated_at` | timestamptz | |

#### Why timestamps, not a date plus two times

The original design used `booking_date` + `start_time` + `end_time`. That cannot express a car
collected on Monday morning and returned on Wednesday evening, which the confirmed vehicle rules
require. Two timestamps express both a two-hour seminar slot and a three-day trip with no special
case, and they let the exclusion constraint use a range type directly instead of reconstructing one
from a date and a time.

Availability grids for venues still query by day — `start_at >= :day AND start_at < :day + 1` —
served by the `(resource_id, start_at)` index.

#### Two approvals on a VMU booking

A vehicle booking that asks the Vehicle Management Unit for a driver needs **two** decisions: the
ordinary booking approval (`approved_at`) and Kulliyyah management approval to use the car
(`management_approved_at`). They are recorded separately because they are made by different people
for different reasons, and a booking that has one but not the other is a real and visible state —
approved for the slot, not yet cleared for the car. Do not collapse them into one flag.

Self-drive bookings leave `management_approved_at` null; nothing else in the system reads it.

#### Why the type-specific columns are nullable rather than a second table

`attendee_count`, `destination` and `passenger_count` apply to one resource kind each. Three nullable
columns on a table that already exists is cheaper than a join table, and the form enforces which
apply based on `resource.resource_type`. Split them out only if vehicle-specific booking fields grow
past a handful.

### `key_handovers`
Decision 17: key collection and return are recorded in the system. One row per booking.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `booking_id` | OneToOne → bookings | `on_delete=PROTECT` |
| `issued_at` | timestamptz | The "time taken" of decision 18 |
| `issued_by_id` | FK → users | The officer handing the key over |
| `returned_at` | timestamptz, null | The "time returned". Null means still out |
| `returned_to_id` | FK → users, null | The officer receiving it |
| `mileage_out`, `mileage_in` | integer, null | **Vehicles only.** `mileage_in` updates `vehicles.current_mileage` |
| `condition_notes` | text | Damage or fault noted at return |
| `created_at`, `updated_at` | timestamptz | |

An outstanding key — `returned_at IS NULL` on a booking whose `end_at` has passed — is the single
most useful operational report in the system. Index accordingly.

**The vehicle key record** AIKOL asked for is this table joined to its booking, not a separate
thing: date out and date in come from `issued_at` / `returned_at`; driver name, contact and staff
number, location from and to, and purpose all come from the booking row. The key register screen
renders them as one record, which is how the administrator thinks about it — but there is only one
copy of each value, so nothing can disagree.

### `email_outbox`
Every message the system sends is written here first, in the same transaction as the action that
caused it, and delivered later by a cron-driven management command.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `to_address` | varchar(254) | Resolved at write time, so a later change of address does not redirect old mail |
| `subject` | varchar(255) | |
| `body` | text | Rendered from a template at write time |
| `template` | varchar(50) | `BOOKING_SUBMITTED`, `BOOKING_APPROVED`, `BOOKING_REJECTED`, `BOOKING_CANCELLED`, `REGISTRATION_VERIFY`, `PASSWORD_RESET` |
| `booking_id` | FK → bookings, null | `on_delete=SET_NULL`. Null for account email |
| `status` | varchar(10) | `PENDING`, `SENT`, `FAILED` |
| `attempts` | integer | Incremented on each delivery attempt |
| `last_error` | text | Truncated SMTP error from the most recent failure |
| `created_at`, `sent_at` | timestamptz | |

**Why a table and not a direct `send_mail()` call.** Three reasons, none of which reopens the
decision to avoid a message queue:

- A booking must not fail because the mail server is slow or down. Writing a row cannot fail in a
  way that loses the booking; an SMTP call can.
- Approving a semester-long series would otherwise hold a request open for dozens of sequential SMTP
  round-trips.
- A failed send is retried and visible. A failed `send_mail()` in a request is gone.

The row is written inside the booking transaction, so a rolled-back booking never emails anyone
about a booking that does not exist. Delivery happens afterwards, out of band.

Sent rows older than 90 days are pruned by the same command — this is operational data, not the
booking record, and it is not covered by the 7-year retention policy.

### `booking_archive`
Same columns as `bookings` plus `archived_at`. Populated before rows are removed from `bookings`.
No foreign keys — it stores denormalised copies of `user_email`, `user_name`, `resource_code` and
`resource_name` so that it survives changes to the live tables.

Note that decision 20 makes **export** the default disposal action, so in normal operation records
leave via a verified CSV. The archive table remains for the archive-in-place option.

### `audit_logs`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | bigint PK | |
| `user_id` | FK → users, null | Null for system-initiated jobs |
| `action` | varchar(50) | `BOOKING_APPROVED`, `RESOURCE_CREATED`, `KEY_ISSUED`, `KEY_RETURNED`, `BULK_IMPORT`, `CLEANUP_RUN`, … |
| `entity_type` | varchar(30) | `booking`, `resource`, `user`, `system` |
| `entity_id` | bigint, null | |
| `description` | text | Human-readable detail. **Never** put a licence or telephone number here |
| `created_at` | timestamptz | |

Append-only. Never edited, never deleted by application code.

### `system_settings`
Key/value configuration so business rules are not hard-coded. Values below are AIKOL's confirmed
answers; they are defaults an administrator may change, not constants.

| Key | Value | Source |
| --- | --- | --- |
| `default_booking_duration` | 120 min | Convenience default on the form |
| `maximum_booking_duration` | 540 min (9 hours) | Decision 8 |
| `bookable_window_start` | 08:00 | Decision 9 |
| `bookable_window_end` | 22:00 | Decision 9 |
| `advance_booking_limit` | 90 days | Decision 7 |
| `cancellation_cutoff` | 72 hours | Decisions 12 and 13 |
| `allow_user_cancel_approved` | true | Decision 12 |
| `cancellation_reason_required` | true | Confirmed follow-up |
| `booking_retention_period` | 7 years | Decision 19 |
| `retention_disposal_action` | `EXPORT` | Decision 20 |
| `maximum_vehicle_trip_days` | 7 | Follow-up decision; AIKOL to confirm the number |
| `maximum_series_occurrences` | 60 | Guard against a runaway recurrence |
| `allowed_email_domains` | `iium.edu.my`, `live.iium.edu.my` | Registration restriction |

#### Site content

The header and footer wording is content, not code. It lives in the same table so the Kulliyyah can
correct an address or a telephone number without a software release — the same argument that put the
booking limits here.

| Key | Default | Appears |
| --- | --- | --- |
| `site_logo` | `aikol_logo.png` | Wordmark in the brand bar. Holds a path under `MEDIA_ROOT`, written by the upload on the site-content screen — never a path typed by hand |
| `site_name` | Room and Vehicle Booking | Beside the wordmark |
| `site_subtitle` | Ahmad Ibrahim Kulliyyah of Laws · IIUM | Small capitals under the name |
| `footer_org` | Ahmad Ibrahim Kulliyyah of Laws | First footer column |
| `footer_address` | Kulliyyah Office, Level 1… | First footer column, newlines preserved |
| `footer_contact_head` | Booking enquiries | Second footer column heading |
| `footer_phone` / `footer_email` / `footer_hours` | 03-6196 4000 · booking-aikol@iium.edu.my · Mon–Fri, 08:30–17:00 | Second footer column |
| `footer_links_head` | IIUM | Third footer column heading |
| `footer_links` | JSON array of `{label, url}` | Third footer column |

`footer_links` is a small ordered list whose entries have no attributes of their own, so it stays a
JSON value rather than becoming a table — the same rule that governed facilities, applied the other
way. Give it a table only when a link needs a status, a role restriction or an ordering of its own.

Editing these is an **administrator** action, never an approver's: it changes what every visitor
sees. Each change is written to `audit_logs` as `SITE_CONTENT_UPDATED` with the acting administrator
and the keys that changed.

## Facilities: why this became a table

This design previously stored facilities as a JSON array on `venues` with a GIN index, on a stated
rule: *"Introduce a separate table only when a facility needs attributes of its own."*

Administrators can now create facilities themselves. The moment they can, a facility needs a stored
display name, an ordering, an active flag and a scope — attributes of its own. The rule's condition
has been met, so the rule says normalise. This is not a reversal of the earlier decision; it is that
decision working as intended.

The JSON approach only ever held together because the nine values were fixed in code, so the
application could map `smart_tv` to "Smart Television" from a constant. An administrator-created
facility has no such constant, and adding one would require a code release to add a facility — which
is precisely what "business rules in `system_settings`, not in the code" exists to prevent.

What the change costs: filtering venues by facility becomes a join rather than a GIN containment
query. At AIKOL's scale — tens of resources, not tens of thousands — this is not measurable. Use
`prefetch_related("facilities")` on any list that displays them, and the "has all of these
facilities" filter becomes a repeated `.filter()` per selected facility, or a `GROUP BY` with a
count, whichever reads better.

### Seed data

Ship the nine existing values as the initial `facilities` rows in a data migration, so the system
starts where the prototype left off: Projector, Microphone, Smart Television, Whiteboard, Computer,
Internet Access, Air Conditioning, Sound System, Video Conferencing. All `applies_to = VENUE` except
Internet Access and Air Conditioning, which are `BOTH`.

Seed them through a data migration rather than a fixture, so a fresh deployment and an existing one
converge on the same list.

## Indexes

Added only where the system actually searches. Every index costs write time and disk.

| Index | Table | Supports |
| --- | --- | --- |
| `(resource_id, start_at)` | bookings | Conflict check and availability display — the hottest query |
| `(user_id, start_at DESC)` | bookings | "My bookings", newest first |
| `(status, start_at)` | bookings | Pending queue, status filters |
| `(start_at)` | bookings | Date-range reports, retention cut-off scans |
| `(series_id)` | bookings | Load or cancel a whole series |
| `booking_reference` unique | bookings | Look-up by reference |
| `(returned_at)` partial, `WHERE returned_at IS NULL` | key_handovers | Outstanding keys report |
| `email` unique | users | Sign-in, import duplicate detection |
| `identification_number` unique | users | Matric/staff look-up, import duplicate detection |
| `code` unique | resources | Import look-up |
| `(resource_type, status)` | resources | Venue and vehicle listing screens |
| `registration_number` unique | vehicles | Plate look-up |
| `code` unique | facilities | Facility look-up and import |
| `(resource_id, facility_id)` unique | resource_facilities | Prevents the same facility twice on one resource |
| `(status, created_at)` | email_outbox | The sender picks up pending mail in order |
| `(entity_type, entity_id)` | audit_logs | History of one booking or resource |
| `(created_at DESC)` | audit_logs | Recent activity panel |

### Overlap exclusion constraint (PostgreSQL)

The application prevents overlaps, but a database-level guarantee means no defect elsewhere can
create one. Using `btree_gist`:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap
EXCLUDE USING gist (
    resource_id                   WITH =,
    tstzrange(start_at, end_at)   WITH &&
) WHERE (status IN ('PENDING', 'APPROVED'));
```

Three things make this correct:

- The `WHERE` clause — rejected and cancelled bookings must not reserve the resource.
- `tstzrange` is half-open, so adjacent bookings (`10:00–12:00` then `12:00–14:00`) do not conflict.
- `resource_id` rather than a venue or vehicle column, so one constraint protects both kinds and a
  multi-day vehicle trip is checked by exactly the same mechanism as a seminar room slot.

SQLite has no equivalent, so in development the application-level check is the only guard. This is
one reason PostgreSQL is required in production.

## Migration notes

- **The first migration must create the custom user model and the `resources` hierarchy.** Django
  cannot change `AUTH_USER_MODEL` after the fact without substantial pain, and retrofitting a shared
  parent table under an existing `venues` table means rewriting every booking foreign key.
- Every schema change is a Django migration committed to version control.
- Take a database backup before applying migrations in production, and copy it to external storage
  (decision 21).
- Long-running index creation on a populated `bookings` table should use `CREATE INDEX CONCURRENTLY`
  (`AddIndexConcurrently` in Django) to avoid locking the table.
- `btree_gist` and the exclusion constraint go in a `RunSQL` migration with a matching reverse
  operation, guarded so the SQLite development database skips it.
