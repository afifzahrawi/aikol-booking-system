# Data retention, archiving, backup and safe deletion

## Governing principle

The system must never destroy institutional data as a side effect of ordinary operation.
Deletion is a deliberate, authorised, logged act — never a default, and never automatic without a
management-approved policy.

Consequences of that principle, applied throughout the codebase:

- Cancelling a booking sets a status; it does not delete a row.
- Deactivating a user or resource sets a status; it does not delete a row.
- Foreign keys from `bookings` to `users` and `resources` use `on_delete=PROTECT`.
- No management command deletes data without an explicit, typed confirmation.

## Retention policy — confirmed

`system_settings.booking_retention_period` = **7 years** (decision 19), chosen for audit purposes.
`system_settings.retention_disposal_action` = **`EXPORT`** (decision 20).

A retention period does not delete anything. It makes records **eligible** for a cleanup that an
administrator must review and confirm.

Seven years of AIKOL bookings is a small dataset. Retention exists here for governance, not for
performance — do not let anyone argue for a shorter period on the grounds of database size.

## Cleanup procedure

```
Retention policy (7 years)
      ↓
Find expired records (end_at < cutoff)
      ↓
Display / log the number affected          ← nothing changed yet
      ↓
Take a database backup                     ← automatic, copied off-server
      ↓
Export to CSV and verify the file          ← the confirmed disposal action
      ↓
Delete in batches of 1,000                 ← each batch its own transaction
      ↓
Write the outcome to the audit log
```

### Three configured actions

| Action | Behaviour | Availability |
| --- | --- | --- |
| **Export and delete** (default) | Write rows to a CSV stored outside the web root, verify the file, then delete from `bookings` | Administrator |
| **Archive** | Copy rows to `booking_archive`, verify the copy, then delete from `bookings` | Administrator |
| **Permanent deletion** | Delete with no copy | Highest administrator level only, where institutional policy permits |

Decision 20 chose export over archive, so the default differs from the original proposal. The
`booking_archive` table remains for the archive option and is not removed — an AIKOL administrator
may still prefer in-database archiving for a particular run.

The exported CSV is the record of last resort. Verify it before deleting anything: row count matches
the selection, the file is readable, and it is stored somewhere that is itself backed up. An export
that lives only on the application server disappears with the application server.

### Batching

Deleting hundreds of thousands of rows in one statement holds locks and bloats the transaction log.
Delete in batches, committing each:

```python
BATCH = 1000
total = 0
while True:
    ids = list(Booking.objects.filter(end_at__lt=cutoff)
                              .values_list("pk", flat=True)[:BATCH])
    if not ids:
        break
    with transaction.atomic():
        export_rows(ids)                        # write and verify first
        Booking.objects.filter(pk__in=ids).delete()
    total += len(ids)
log_action("CLEANUP_RUN", description=f"{total} records exported and removed, cutoff {cutoff}")
```

Export before delete, inside the same transaction, so a failure cannot leave rows deleted but
unexported.

`KeyHandover` rows reference bookings with `on_delete=PROTECT`, so they are exported and removed in
the same batch, before the bookings they belong to. A cleanup that forgets them will simply fail
rather than orphan anything — which is the intended behaviour, not a defect to work around by
loosening the foreign key.

### Safeguards

- Preview is always available and changes nothing.
- The affected count is shown **before** any action.
- Permanent deletion requires typing `DELETE <n> RECORDS`, where `<n>` is the actual count.
- Every run is written to `audit_logs` with the actor, cutoff, action and totals.
- The job never runs unattended unless management has explicitly approved a schedule.

## Full database reset

A destructive command for development, testing and migration — **not** a normal production
operation. Kept entirely separate from retention.

Requirements:

- Highest administrator level only.
- Disabled by default in `production.py` (a settings flag must be explicitly enabled).
- States exactly what will be destroyed, with counts.
- Requires the phrase `DELETE ALL DATA` typed in full.
- Requires a backup to be taken first.
- Never appears among ordinary administrative actions in the interface.
- Written to the audit log.

## Backup — confirmed

Decision 21: a backup is required before any bulk deletion, and backups are held on **external
storage**. Because hosting is self-provided rather than run by IIUM ITD (decisions 22 and 23), no
institutional backup service stands behind this — the schedule below is the whole of it.

| Measure | Policy |
| --- | --- |
| Nightly | Full `pg_dump`, retained 14 days |
| Weekly | One dump retained 8 weeks |
| Before migrations | On demand, automatic in the deploy script |
| Before bulk deletion | On demand, automatic in the cleanup job |
| Storage | **Copied off the server** to external storage (decision 21). A dump sitting on the same VPS is not a backup — it dies with the machine |
| Encryption | Backups leave the server, so encrypt at rest. The passphrase is not stored on the server |
| Verification | Monthly test restore into a scratch database |

AIKOL still needs to name the external storage destination; that is an open operational item in
section 5 of `CLAUDE.md` and must be settled before go-live, not after.

### Restore

The restore procedure must be **written down and tested on a non-production server before the
system carries real bookings**. A backup that has never been restored is not a backup.

```bash
# Backup
pg_dump --format=custom --file=/var/backups/aikol/aikol_$(date +%F).dump aikol_booking

# Restore into a clean database
createdb aikol_restore_test
pg_restore --dbname=aikol_restore_test /var/backups/aikol/aikol_2026-08-13.dump
```

Note for restores: the exclusion constraint and the `btree_gist` extension must exist in the target
database. `pg_restore` recreates both from a custom-format dump, but a hand-built scratch database
will silently accept overlapping rows without them.
