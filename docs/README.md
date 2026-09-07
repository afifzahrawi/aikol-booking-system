# Developer documentation — AIKOL Room and Vehicle Booking System

This directory holds technical documentation for developers. It is **not** the material
presented to AIKOL management — that is `management-report/index.html`, an HTML document
intended to be read in a browser and printed to PDF.

## Contents

| Document | Covers |
| --- | --- |
| [technical/architecture.md](technical/architecture.md) | Application structure, Django app layout, request and registration flows, scheduled jobs, deployment topology |
| [technical/database-schema.md](technical/database-schema.md) | Tables, the shared `resources` design, facilities, the email outbox, indexing strategy, migration notes |
| [technical/booking-rules.md](technical/booking-rules.md) | The overlap rule, status lifecycle, venue and vehicle rules, recurrence, cancellation, key handover, confirmation email, concurrency handling |
| [technical/data-retention.md](technical/data-retention.md) | Retention policy, export and archiving, batched deletion, backup and restore |
| [technical/security.md](technical/security.md) | Authentication, self-registration, the three roles, personal data, upload handling, destructive-operation safeguards, server operations |
| [technical/testing-strategy.md](technical/testing-strategy.md) | What must be tested, the required conflict, recurrence, vehicle, key, email and facility tests, performance checks |
| [technical/bulk-import.md](technical/bulk-import.md) | CSV formats, validation rules, transaction behaviour |
| [technical/prototype-guide.md](technical/prototype-guide.md) | How the Phase 1 prototype is built, how to regenerate its assets, and where it is now out of date |

## Project status

Phase 1 (discovery, management report, prototype) is complete, and **AIKOL has answered all 26
decisions** in section 24 of the management report. Phase 3 is authorised.

The answers changed the scope: vehicle booking, recurring bookings, key custody tracking, a separate
Approver role, self-registration, booking confirmation email and an administrator-managed facility
list are all in the first release, and several of them were previously listed as out of scope.
The documents in `technical/`, the prototype and the management report have all been brought into
line with the answers. Section 24 of the report now records AIKOL's responses, and the prototype
covers vehicles, key custody, facilities and self-registration across nineteen screens.

The authoritative summary of project direction, decisions and current status is
[`CLAUDE.md`](../CLAUDE.md) in the repository root. Section 5 of that file lists every confirmed
decision and is the thing to read before writing any code. Update it whenever architecture,
requirements, schema or major features change.

AIKOL's own answers are kept verbatim in `Section 24.docx` at the repository root. That file is
never edited; clarifications are recorded in `CLAUDE.md` instead.
