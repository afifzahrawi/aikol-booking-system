# Bulk import and export

## Why CSV

Any officer can produce a CSV from a spreadsheet. No special tooling, no format negotiation, and
the file can be corrected and re-uploaded. The prototype screen
(`prototype/data-management.html`) demonstrates the intended workflow.

## Import workflow

```
Download template → Upload CSV → Validate → Preview + row errors
    → Confirm → Single transaction, bulk insert → Summary + audit log
```

Nothing is written to the database until the administrator confirms. The preview is generated
entirely from validation results.

## File formats

### Users — `aikol-users-template.csv`

```
name,email,identification_number,phone,affiliation,role,status
```
- `name` required.
- `email` required, well-formed, ending `@iium.edu.my` or `@live.iium.edu.my`, must not already
  exist, must not repeat within the file.
- `identification_number` required — matriculation or staff number (decision 18). Unique, and
  checked for duplicates both in the database and within the file.
- `phone` required (decision 18).
- `affiliation` one of `Student`, `Lecturer`, `Staff`.
- `role` one of `User`, `Approver`, `Administrator`.
- `status` one of `Active`, `Inactive`.
- No password column. Imported accounts receive an activation link and set their own password.
- No licence columns. Driving licence details are entered by the user at their first vehicle
  booking, not bulk-loaded by an administrator.

Imported accounts are created with `email_verified = False`. Setting a password through the
activation link verifies the address, so an imported user follows the same proof-of-mailbox path as
a self-registered one.

### Venues — `aikol-venues-template.csv`

```
code,name,building,floor,venue_type,capacity,facilities,bookable_window_start,bookable_window_end
```
- `code` required, unique across **all resources** — venues and vehicles share the `resources.code`
  namespace, so a venue cannot take a code a vehicle already holds.
- `capacity` a positive whole number.
- Times as `HH:MM`, closing after opening. Leave both blank to inherit the 08:00–22:00 system
  default (decision 9).
- `facilities` is a pipe-separated list of **facility codes**, not display names —
  `projector|whiteboard|aircond`. An unknown code is a row error, never a silent creation: a typo in
  a spreadsheet must not quietly add "projecter" to the facility list for everyone.
- Import the facilities first if the venue file references codes that do not exist yet.
- Description and rules are edited after import — they do not compress well into CSV.

### Facilities — `aikol-facilities-template.csv`

```
code,name,applies_to,display_order,status
```
- `code` required and unique. Lower-case, no spaces — it is referenced by the venue and vehicle
  templates and by saved filter URLs.
- `name` required. The display label, freely editable afterwards.
- `applies_to` one of `Venue`, `Vehicle`, `Both`.
- `status` one of `Active`, `Inactive`.
- Re-importing an existing `code` **updates** the name, order and status rather than failing. This
  is the one template where that is true, because a facility list is maintained rather than loaded
  once, and because the code is the stable identity that resources are already linked to.

### Vehicles — `aikol-vehicles-template.csv`

```
code,name,registration_number,vehicle_class,make,model,year,seats,transmission,fuel_type,facilities,road_tax_expiry,insurance_expiry,current_mileage
```
- `code` required, unique across all resources.
- `registration_number` required and unique.
- `vehicle_class` is `Car` in the first release; other values are rejected until the class is
  supported.
- `seats` a positive whole number; `transmission` one of `Auto`, `Manual`.
- `road_tax_expiry` and `insurance_expiry` as `YYYY-MM-DD`. **A date already in the past is a
  warning, not an error** — an administrator may well be loading a fleet mid-renewal, and refusing
  the import would be unhelpful. The vehicle simply cannot be booked until the date is updated.
- `facilities` uses the same pipe-separated codes as the venue template, limited to facilities whose
  `applies_to` is `Vehicle` or `Both`.
- Description, rules and images are edited after import.

### Historical bookings — `aikol-bookings-template.csv`

```
booking_reference,user_email,resource_code,start_at,end_at,purpose,attendee_count,destination,passenger_count,status
```
- `user_email` must match an existing account; `resource_code` an existing resource.
- `start_at` and `end_at` as `YYYY-MM-DD HH:MM`, end after start. Timestamps rather than a date plus
  two times, because a historical vehicle trip may span days.
- `attendee_count` applies to venue rows; `destination` and `passenger_count` to vehicle rows. A
  value in a column that does not apply to the row's resource type is a row error, not a silent
  discard — it usually means the wrong resource code.
- `status` normally `Completed` or `Cancelled` for historical data.
- Rows that overlap an existing active booking, or another row in the same file, are reported as
  errors rather than silently accepted.
- No `series_id` column. Historical recurrence is not reconstructed on import; each occurrence
  arrives as an independent booking.

## Validation rules

Applied per row before any insert:

1. Required columns present in the header (case-insensitive); otherwise the file is rejected outright.
2. Column count per row matches the header.
3. Field-level format checks (email, domain, timestamp, integer, enumerated values).
4. Duplicate detection against the database (`email`, `identification_number`, `resources.code`,
   `registration_number`, `booking_reference`).
5. Duplicate detection within the file itself.
6. Referential checks for bookings (user and resource must exist) and for resources (every facility
   code must exist and be active).
7. Resource-type checks for bookings — the supplied columns must match the resource kind.
8. Overlap checks for bookings, against both the database and earlier rows in the file.

Each failing row is reported with its **line number** and every reason it failed, so an
administrator can correct the spreadsheet in one pass.

## Transaction behaviour

```python
with transaction.atomic():
    Model.objects.bulk_create(objects, batch_size=500)
    log_action("BULK_IMPORT", description=f"{len(objects)} {model_name} imported, {skipped} skipped")
```

- One transaction for the whole import: if any statement fails, nothing is written.
- `bulk_create` with a batch size — never one `INSERT` per row.
- Valid rows may be imported while invalid rows are skipped, but only when the administrator has
  seen the error list and confirmed.

**`bulk_create` and multi-table inheritance do not mix.** `Venue` and `Vehicle` inherit from
`Resource`, and Django cannot bulk-create a child model whose parent row must be inserted first.
Resource imports therefore insert the `Resource` rows in bulk, then the child rows in bulk against
the returned primary keys — inside the same transaction. Booking imports are unaffected and use
plain `bulk_create`.

## Limits

- Maximum file size 10 MB, enforced server-side.
- Files are parsed in a streaming fashion; the whole file is not held in memory as one string.
- If profiling later shows imports are too slow to run inside a request, move them to a management
  command run from the server. A message queue is **not** introduced unless measurement proves it
  necessary.

## Export

- Booking records (filtered by date range, status and resource type), venue list, vehicle list,
  facility list, user accounts, and the retention export described in `data-retention.md`.
- Venue and vehicle exports emit `facilities` in the same pipe-separated code format the import
  accepts, so an export can be edited and re-imported without translation.
- Generated server-side and streamed with `StreamingHttpResponse` in batches, so a large export
  does not exhaust memory.
- Limited to what the requesting administrator is authorised to see. An approver may export the
  bookings they can decide; nothing else.
- Password hashes are never included in any export.
- Personal identifiers — matriculation number, telephone, driving licence — appear only in the user
  export, whose purpose requires them. They are not in utilisation or booking reports. See
  `security.md`.
- Each export is written to the audit log.
