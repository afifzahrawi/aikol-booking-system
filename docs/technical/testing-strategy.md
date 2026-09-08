# Testing strategy

Django's built-in test framework (`python manage.py test`). No additional paid tooling.
Tests are part of the deliverable, not an optional extra: the conflict rules in particular are the
system's core promise and must be demonstrably correct.

## Required: booking conflict tests

These are mandatory and must exist before the booking feature is considered complete. Against an
existing **10:00–12:00** booking on a given resource and date:

| Case | New request | Expected |
| --- | --- | --- |
| Identical period | 10:00–12:00 | **Rejected** |
| Partial overlap (late) | 11:00–13:00 | **Rejected** |
| Partial overlap (early) | 09:00–11:00 | **Rejected** |
| Inside existing | 10:30–11:00 | **Rejected** |
| Surrounding existing | 09:00–13:00 | **Rejected** |
| Adjacent before | 08:00–10:00 | **Accepted** |
| Adjacent after | 12:00–14:00 | **Accepted** |
| Different resource, same time | 10:00–12:00 | **Accepted** |
| Different date, same time | 10:00–12:00 | **Accepted** |
| Existing booking is `REJECTED` | 10:00–12:00 | **Accepted** (rejected bookings do not reserve) |
| Existing booking is `CANCELLED` | 10:00–12:00 | **Accepted** |
| Existing booking is `PENDING` | 10:00–12:00 | **Rejected** (pending reserves the slot) |

**Run this entire table twice — once with a venue, once with a vehicle.** The rule is shared, so the
results must be identical. If they ever diverge, something has grown a resource-specific code path
that should not exist. Parameterise the fixture rather than copying the tests.

### Multi-day overlap

Vehicles can be booked across days, which the original date-plus-time design could not express.
Against an existing trip from **Monday 08:00 to Wednesday 17:00**:

| Case | New request | Expected |
| --- | --- | --- |
| Fully inside | Tuesday 09:00–11:00 | **Rejected** |
| Straddles the start | Sunday 20:00 – Monday 10:00 | **Rejected** |
| Straddles the end | Wednesday 16:00 – Thursday 09:00 | **Rejected** |
| Encloses entirely | Sunday 06:00 – Friday 18:00 | **Rejected** |
| Ends exactly at the start | Sunday 20:00 – Monday 08:00 | **Accepted** |
| Starts exactly at the end | Wednesday 17:00 – Thursday 09:00 | **Accepted** |

### Concurrency

Two simultaneous submissions for the same slot must result in exactly one booking. Test with
`TransactionTestCase` and two threads, asserting that one raises a validation error or
`IntegrityError` and that the database ends with a single row. This test proves the
`select_for_update()` lock and the exclusion constraint actually work.

### Approval-time re-check

A `PENDING` request whose slot was taken by another approved booking after submission must fail on
approval, not overwrite it.

## Required: recurring booking tests

Recurrence is new scope (decision 15) and is where a conflict bug is most likely to hide, because a
series touches dozens of slots at once.

| Case | Expected |
| --- | --- |
| Weekly series over a clear semester | Every occurrence created, all carrying the same `series_id` |
| Series where one week clashes | The clash is **reported to the user**, never silently skipped |
| User accepts the partial series | Non-clashing occurrences created; the clashing week is absent |
| Series exceeding `maximum_series_occurrences` | Refused before any row is created |
| Series ending before it starts | Refused |
| Cancel whole series | Every future occurrence becomes `CANCELLED` with the reason; past ones untouched |
| Approve whole series | Every occurrence re-checked for conflicts at approval time |
| Occurrence cancelled individually | Only that row changes; the series and its siblings are unaffected |
| Series expansion is atomic | A failure partway leaves **no** occurrences, not a partial series |

## Required: vehicle rule tests

| Case | Expected |
| --- | --- |
| Student requests a vehicle with a VMU driver | **Accepted** — students may book, they may not drive |
| Student submits `driver_arrangement = SELF` | Refused by the view, not only by the form |
| Lecturer requests a vehicle, self-drive | Accepted |
| VMU booking | Records that Kulliyyah management approval is also required; not usable until both approvals exist |
| Administrator books a vehicle on a student's behalf | Accepted; `user_id` is the student, `created_by_id` the administrator |
| Self-drive with no licence on file | Refused with a prompt to add it |
| Self-drive licence expires before the trip ends | Refused |
| VMU booking with no licence on file | **Accepted** — the requester is not the driver |
| Road tax expires before the trip ends | Refused, and the reason given to the requester names no date |
| `passenger_count` exceeds `vehicle.seats` | Refused |
| Trip longer than `maximum_vehicle_trip_days` | Refused |
| Venue booking longer than 9 hours | Refused |
| **Vehicle trip spanning 3 days** | **Accepted** — the 9-hour venue limit must not be applied to vehicles |

That last pair is the important one. The duration limit is chosen from `resource_type`, and applying
the venue rule to a car would make multi-day trips impossible while every other test still passed.

## Required: key handover tests

| Case | Expected |
| --- | --- |
| Issue a key for an `APPROVED` booking | `KeyHandover` created with `issued_at` and `issued_by` |
| Issue a key for a `PENDING` booking | Refused |
| Return a key | `returned_at`, `returned_to` recorded |
| Booking past `end_at` with no return | Appears in the outstanding-keys report |
| Booking reaches `COMPLETED` with key outstanding | Allowed — the two are tracked separately, and the key stays outstanding |
| Both actions | Written to the audit log |

## Required: confirmation email tests

Use Django's `locmem` email backend and assert on `email_outbox` rows, not on `mail.outbox` alone —
the outbox table is where the system's own guarantee lives.

| Case | Expected |
| --- | --- |
| Booking submitted | One `PENDING` outbox row, template `BOOKING_SUBMITTED`, addressed to `booking.user` |
| Booking approved / rejected / cancelled | One row each, correct template, rejection and cancellation reasons present in the body |
| Booking made on behalf of a user | Addressed to `user`, **not** to `created_by` |
| Booking transaction rolls back | **No** outbox row survives — the write is inside the same transaction |
| SMTP raises during sending | Row becomes `FAILED` with `attempts` incremented; the booking is untouched; a later run retries it |
| Series approved | **One** summary email, not one per occurrence |
| Single occurrence cancelled | One email for that occurrence only |
| Body content | Contains no matriculation number, telephone number or licence number |
| Pruning | `SENT` rows older than 90 days are removed; `PENDING` and `FAILED` rows are not |

The rollback case is the one worth writing first. A `send_mail()` call placed outside the
transaction will pass every other test here and still email users about bookings that were never
created.

## Required: facility tests

| Case | Expected |
| --- | --- |
| Administrator creates a facility | Created with a generated unique `code` |
| Administrator renames a facility | `name` changes, `code` does not; resources keep their link |
| Duplicate facility code | Refused |
| Deactivate a facility in use | Hidden from forms and filters; resources that have it are unchanged |
| Delete a facility in use | Refused — `on_delete=PROTECT` on the join |
| Delete an unused facility | Permitted |
| Approver attempts facility management | 403 |
| Standard user attempts facility management | 403 |
| `applies_to = VENUE` | Not offered on the vehicle form |
| Venue list filtered by two facilities | Returns only venues having **both** |
| Seed migration | The nine original facilities exist after migrating a fresh database |

## Other areas

| Area | Tests |
| --- | --- |
| Registration | Non-IIUM domain refused; duplicate email refused; duplicate matriculation number refused; unverified account cannot book; verification link works once and expires |
| Authentication | Sign-in, sign-out, inactive account rejected, password reset flow |
| Authorisation | Standard user receives 403 on every admin URL; **approver receives 403 on user, resource, settings and retention URLs**; a user cannot view or cancel another user's booking |
| Booking on behalf | Administrator may set `user_id` to another account; a standard user may not; audit entry written |
| Booking validation | End before start, outside 08:00–22:00, over the duration limit, past date, beyond the 90-day advance limit, attendees over capacity, inactive resource |
| Cancellation | Allowed more than 3 days ahead; **refused inside the 72-hour cutoff**; **refused with an empty reason**; record retained with status `CANCELLED`; slot released |
| Status transitions | Only legal transitions permitted; rejection requires a reason |
| Resources | Deactivation hides the resource from booking screens but retains its bookings; a venue and a vehicle both round-trip through the shared `Resource` queries |
| Users | Deactivation retains bookings; deletion is prevented while bookings reference the account |
| CSV import | Missing columns, malformed email, unknown affiliation, duplicate in file, duplicate in database, invalid capacity, unknown resource code, atomic rollback on failure |
| Retention | Correct records selected for the 7-year cutoff, **export written and verified before delete**, batching, audit entry created |
| Audit log | An entry is written for each administrative action, and **contains no licence or telephone number** |
| Reports | Aggregations return correct counts for a known fixture |
| Query counts | A venue list showing facilities uses `prefetch_related` and does not issue one query per venue |

## Performance checks

Not a formal load test — a sanity check that the design holds at scale.

1. Load a fixture of ~200,000 bookings across several years, venues and vehicles.
2. Assert that the booking list, the resource availability view and the admin booking list each
   issue a bounded number of queries (`assertNumQueries`) and do not degrade with table size.
3. Confirm the conflict query uses the `(resource_id, start_at)` index (`EXPLAIN ANALYZE`).
4. Confirm a full-semester recurrence submission stays within an acceptable request time. If it does
   not, the fix is a smarter query, not a message queue — see `CLAUDE.md` section 13.
5. Confirm no screen loads an unbounded queryset — pagination is applied in the query, not in the
   template.

## A note on SQLite

The exclusion constraint exists only in PostgreSQL, so a test suite run against SQLite passes with
the last line of defence missing. **Run the conflict and concurrency tests against PostgreSQL in
CI**, or they are not testing what they claim to test.

## Accessibility and browser checks

Manual, before each release: keyboard navigation through the booking form, visible focus, form
labels present, contrast adequate, and pages usable at 360 px width.

## Definition of done for a feature

- Server-side validation implemented, browser validation treated as convenience only.
- Tests written for the success path and each failure path.
- Where the feature touches bookings, tested against **both** a venue and a vehicle.
- Audit log entry written where the action is administrative.
- Pagination and filtering applied in the query for any list screen.
- `CLAUDE.md` updated if the architecture, schema or requirements changed.
