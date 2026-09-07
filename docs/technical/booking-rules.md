# Booking rules

These rules implement the decisions confirmed by AIKOL. Section 5 of `CLAUDE.md` is the authority
for the values; this document is the authority for the behaviour.

"Resource" below means a venue or a vehicle. The rules are identical for both except where a
heading says otherwise.

## Status lifecycle

```
Created ──► PENDING          (every resource requires approval — decision 4)
              │
    ┌─────────┴─────────┐
    ▼                   ▼
APPROVED            REJECTED
    │
    ├──► COMPLETED   (scheduled job, once the booked period has passed)
    └──► CANCELLED   (requester within the cutoff, or an approver/administrator at any time)
```

| Status | Reserves the resource | Set by |
| --- | --- | --- |
| `PENDING` | **Yes** | System, on submission |
| `APPROVED` | **Yes** | Approver or administrator |
| `REJECTED` | No | Approver or administrator, with a mandatory reason |
| `CANCELLED` | No | Requester (subject to the cutoff) or approver/administrator (any time), always with a reason |
| `COMPLETED` | No | Scheduled job, once the booked period has passed |

`PENDING` deliberately reserves the slot so that two users cannot both submit a request for the
same period and both wait for a decision.

Decision 4 makes every resource require approval, so `approval_required = false` produces no
bookings in the first release. The code path stays — the field is a setting AIKOL may relax, not a
constant — but nothing ships with it set.

## The overlap rule

For a given resource, a new booking conflicts with an existing one when:

```
new_start < existing_end  AND  new_end > existing_start
```

applied **only** to existing bookings whose status is `PENDING` or `APPROVED`.

Adjacent bookings do not conflict: one ending at 12:00 and one starting at 12:00 are both valid.
The comparison is strict (`<`, `>`), not inclusive.

Because `start_at` and `end_at` are timestamps rather than a date plus two times, this single rule
covers a two-hour seminar room slot and a three-day outstation car trip with no special case.

```python
BLOCKING_STATUSES = (Booking.Status.PENDING, Booking.Status.APPROVED)

def conflicting_bookings(resource, start_at, end_at, exclude_pk=None):
    qs = Booking.objects.filter(
        resource=resource,
        status__in=BLOCKING_STATUSES,
        start_at__lt=end_at,
        end_at__gt=start_at,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs
```

## Three layers of enforcement

1. **Browser** — live feedback as the form is completed. Convenience only; never trusted.
2. **Server** — checked on submission *and* again on approval, inside `transaction.atomic()` with
   `select_for_update()` over the resource's bookings in the affected window. This closes the race
   between two simultaneous requests.
3. **Database** — the PostgreSQL exclusion constraint in `database-schema.md`. Even a defective
   code path cannot produce an overlap; it raises `IntegrityError`, which the view converts into a
   normal validation message.

```python
with transaction.atomic():
    # Lock this resource's overlapping bookings so a concurrent request cannot slip in
    # between the check and the insert.
    clash = (Booking.objects
             .select_for_update()
             .filter(resource=resource,
                     status__in=BLOCKING_STATUSES,
                     start_at__lt=end_at,
                     end_at__gt=start_at)
             .exists())
    if clash:
        raise ValidationError("The resource is already reserved for the selected period.")
    booking = Booking.objects.create(...)
```

Re-checking at approval time matters: a request may have been submitted when the slot was free and
approved after another booking was confirmed for it.

## Validation common to both resource kinds

Enforced on the server, all limits read from `system_settings` rather than hard-coded.

| Rule | Confirmed value | Source |
| --- | --- | --- |
| `end_at > start_at` | — | Model check constraint and form validation |
| Times within the bookable window | 08:00–22:00 | Decision 9; `resource.bookable_window_*` may narrow it |
| Duration ≤ maximum | 9 hours | Decision 8 |
| Start not in the past | — | Form validation |
| Start ≤ today + advance limit | 90 days | Decision 7 |
| Resource status is `ACTIVE` | — | Form validation |
| Requesting user status is `ACTIVE` and `email_verified` | — | Permission check |

Weekends, public holidays and semester breaks are all bookable (decisions 10 and 11). There is no
holiday calendar and none is needed.

**Decision 8 caps a single booking at nine hours, it does not cap the day.** A user needing a room
from 08:00 to 20:00 submits two bookings. Do not silently merge or extend them; the second booking
is checked against the first like any other.

## Venue-specific rules

| Rule | Detail |
| --- | --- |
| Eligibility | Any active, verified user — students included, all venues (decisions 2 and 3) |
| `attendee_count` | Required, `≤ venue.capacity` |
| Same-day only | A venue booking starts and ends on the same date |

## Vehicle-specific rules

Vehicles were added after section 24 was answered; these come from the follow-up decisions recorded
in `CLAUDE.md` section 5.

| Rule | Detail |
| --- | --- |
| Eligibility to book | **Any active, verified user**, students included |
| Multi-day | Permitted. Trip length ≤ `maximum_vehicle_trip_days` |
| Driver arrangement | `SELF` or `VMU`. **`SELF` requires `affiliation in (LECTURER, STAFF)`** and a licence on file. A student may only submit `VMU` — enforce it in the form *and* the view |
| VMU driver | The Vehicle Management Unit supplies the driver, requested through STADD. Needs Kulliyyah management approval as well as the booking approval, so a VMU booking is not usable until both are recorded |
| Driver details | `driver_name`, `driver_contact`, `driver_staff_no` — recorded on every vehicle booking, whoever drives. For self-drive they default from the requester's own account |
| Locations | `origin` and `destination` — where the car leaves from and where it is going. Both required |
| Licence expiry | Self-drive only: must be later than `end_at` — refuse a trip that outlives the licence. Not checked for a VMU booking, because the VMU driver is not the requester |
| Road tax and insurance | `vehicle.road_tax_expiry` and `insurance_expiry` must be later than `end_at` |
| `destination` | Required |
| `passenger_count` | Required, `≤ vehicle.seats` |

The nine-hour maximum duration applies to venues. For vehicles the governing limit is
`maximum_vehicle_trip_days`; a multi-day trip that also had to fit in nine hours would be a
contradiction. Enforce the correct limit from `resource.resource_type` — this is an easy rule to get
wrong and it deserves a test of its own.

## Recurring bookings

Decision 15 puts recurrence in the first release, so a semester's teaching can be entered once.

A `BookingSeries` is a **template**. It reserves nothing. Submitting a series:

1. Expand the definition into concrete occurrences between `series_start_date` and
   `series_end_date`, refusing more than `maximum_series_occurrences`.
2. Validate every occurrence against the rules above.
3. Inside one `transaction.atomic()`, check every occurrence for conflicts with
   `select_for_update()`.
4. **If some occurrences clash, do not silently skip them and do not abandon the series.** Return
   the clashing dates to the user and let them choose: submit the remainder, or change the request.
   A user who books a semester and is told "24 of 26 weeks were created, weeks 7 and 12 clash with
   an existing booking" can act. A user who is told nothing discovers it in week 7.
5. Create the surviving occurrences as ordinary `bookings` rows carrying `series_id`.

Occurrences are never computed at read time. A booking that is not a row is invisible to the
exclusion constraint, which would quietly defeat the guarantee that the whole design rests on.

Approving, rejecting or cancelling may act on one occurrence or on the whole series. A series
action is a loop over rows in one transaction, applying the same per-occurrence rules — there is no
separate series-level status.

## Cancellation

Cancellation **never deletes the record**. It sets `status = CANCELLED`, records
`cancellation_reason`, `cancelled_by` and `cancelled_at`, and releases the slot.

**A reason is mandatory for every cancellation, by anyone** (confirmed follow-up decision;
decision 13 requires "a reasonable excuse"). The form rejects an empty or whitespace-only reason.

| Actor | Rule |
| --- | --- |
| Requester, `PENDING` booking | Allowed at any time before the start |
| Requester, `APPROVED` booking | Allowed if the start is **more than 3 days away** (decision 13, `cancellation_cutoff` = 72 hours) |
| Requester, inside the cutoff | Not allowed through self-service. They must contact the Kulliyyah office, which cancels on their behalf |
| Requester, other statuses | Not allowed |
| Approver or administrator | Allowed at any time, for any status that reserves the resource; reason written to the audit log |

Decision 12 reads "Cancel only. Approval needs to be approved by Admin." Clarified directly with
AIKOL: **users cancel their own bookings outright.** There is no cancellation-approval workflow and
no `CANCELLATION_REQUESTED` status. The phrase refers to booking *approval*, which remains an
administrator and approver function.

Ownership is checked on the record, not inferred from the URL.

## Key issue and return

Decision 17 requires key custody to be recorded. A `KeyHandover` row is created when the key is
handed over and updated when it comes back.

| Step | Effect |
| --- | --- |
| Issue | `issued_at`, `issued_by`. For a vehicle, `mileage_out`. Only for an `APPROVED` booking |
| Return | `returned_at`, `returned_to`, `condition_notes`. For a vehicle, `mileage_in`, which updates `vehicle.current_mileage` |

Both actions are written to the audit log as `KEY_ISSUED` and `KEY_RETURNED`. A booking whose
`end_at` has passed with `returned_at IS NULL` is an **outstanding key** and appears on the
administrator dashboard until resolved. Key issue does not change the booking status, and a booking
may reach `COMPLETED` with a key still outstanding — the two are tracked separately on purpose,
because chasing an unreturned key must not depend on someone remembering not to close the booking.

## Confirmation email

Every status change emails the person the booking is **for** — `booking.user`, not
`booking.created_by`. When an administrator books on someone's behalf, the requester is the one who
needs to know; the administrator already does.

| Trigger | Template | Contains |
| --- | --- | --- |
| Submitted | `BOOKING_SUBMITTED` | Reference, resource, period, purpose, and that it is awaiting approval |
| Approved | `BOOKING_APPROVED` | The above, plus where and when to collect the key |
| Rejected | `BOOKING_REJECTED` | The mandatory rejection reason |
| Cancelled | `BOOKING_CANCELLED` | Who cancelled it and the mandatory reason |

These are transactional messages about the user's own booking, so there is no opt-out in the first
release. Reminders before a booking, and chasing an outstanding key, are separate ideas and are not
in scope.

### How it is sent

The message is written to `email_outbox` **inside the same transaction** as the status change, and
delivered afterwards by the cron sender. Two consequences that matter:

- A rolled-back booking never emails anyone about a booking that does not exist.
- A mail server outage delays confirmations. It does not fail bookings.

Never call `send_mail()` directly from a view. See `database-schema.md` for the outbox table.

### Recurring series

**One email per series action, not one per occurrence.** Approving a semester of weekly bookings
must not send 26 messages. The series templates summarise: the resource, the pattern, the date
range, the number of occurrences created or approved, and any dates that clashed and were left out.

An occurrence acted on individually emails individually, as any other booking does. The rule is
simply that a series action produces a series email.

## Booking reference

Format `BK-YYYYMM-NNNN`, unique. Generate inside the same transaction as the booking, using a
sequence or a `SELECT ... FOR UPDATE` on a counter row — not `COUNT(*) + 1`, which races. Every
occurrence in a series gets its own reference; the series is not itself referenced by users.

## `COMPLETED` transition

A daily scheduled job (cron calling a management command) moves `APPROVED` bookings whose `end_at`
has passed to `COMPLETED`. It is idempotent and safe to run repeatedly. It never touches `PENDING`
bookings — a request that was never decided should remain visible as such rather than being silently
closed.
