# Architecture

## Shape of the system

A single Django project — a modular monolith. One codebase, one deployment, one database.
There is no separate frontend application, no message broker and no external service dependency
beyond an SMTP server for account and booking email.

```
Browser (desktop / tablet / mobile)
        │  HTTPS
        ▼
Nginx  — TLS termination, static and media files
        │
        ▼
Gunicorn → Django application
        │      accounts · resources · bookings · administration
        │      reporting · importexport · notifications · audit
        ▼
Django ORM
        ▼
PostgreSQL (production) / SQLite (development)
        │
        ▼
Server file system — resource images, CSV exports, database backups
        │
        ▼
External storage — off-server backup copies (decision 21)

cron ──► manage.py send_queued_email   (every 5 minutes)
    ├──► manage.py complete_bookings   (daily)
    └──► manage.py backup_database     (daily, then copy off-server)

SMTP ◄── email_outbox table, drained by send_queued_email
```

## Why a monolith

The modules share the same data and the same users at the same time. Splitting them into
services would add network calls, partial failures and deployment coordination in exchange for
scaling properties this system will never need. Keeping module boundaries clean *inside* one
application preserves the option to split later.

## Proposed Django project layout

```
aikol_booking/
├── manage.py
├── requirements.txt
├── config/                     # project package
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py      # SQLite, DEBUG=True, console email backend
│   │   └── production.py       # PostgreSQL, DEBUG=False, security headers, SMTP
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/               # custom user model, registration, roles, auth views
│   ├── resources/              # Resource base + Venue + Vehicle, facilities, images, browsing
│   ├── bookings/               # Booking, BookingSeries, KeyHandover, conflict rules, workflow
│   ├── administration/         # dashboards, settings, data management screens
│   ├── reporting/              # aggregate queries, dashboard data, exports
│   ├── importexport/           # CSV templates, validation, bulk insert
│   ├── notifications/          # email outbox, templates, cron sender
│   └── audit/                  # audit log model + helper
├── templates/                  # Django templates (base.html + per-app)
├── static/                     # Bootstrap 5, Bootstrap Icons, project CSS/JS (vendored, not CDN)
├── media/                      # uploaded resource images (not in version control)
└── tests/                      # or per-app tests.py / tests/ package
```

### Module responsibilities

| App | Owns |
| --- | --- |
| `accounts` | User model, affiliation and role, self-registration and email verification, sign-in/out, password reset, activation/deactivation |
| `resources` | `Resource` base model with `Venue` and `Vehicle` subclasses, `Facility` and the resource-facility join, `ResourceImage`, listing, filtering, detail pages, image upload, facility management |
| `bookings` | `Booking`, `BookingSeries`, `KeyHandover`, conflict detection, status transitions, recurrence expansion, cancellation rules, key issue and return |
| `administration` | Admin dashboards, system settings, retention and reset screens |
| `reporting` | Aggregations for dashboards, CSV export generation, outstanding-keys report |
| `importexport` | CSV parsing, row validation, preview, bulk insert |
| `notifications` | `EmailOutbox` model, message templates, a single `queue_email()` helper, and the `send_queued_email` command |
| `audit` | `AuditLog` model and a single `log_action()` helper used by all other apps |

Rule: apps may import models and helpers from `accounts`, `resources`, `notifications` and `audit`.
Nothing imports from `administration` or `reporting` — those are leaves.

### Why venues and vehicles share one app

`Venue` and `Vehicle` both inherit from `Resource`, and `Booking` points at `Resource`. Splitting
them into two apps would put a model and its subclass on either side of an app boundary for no gain,
and would invite a second booking implementation. See `database-schema.md` for the full argument.

## Request flow for a booking submission

1. `BookingCreateView` renders the form for the chosen resource; the template shows client-side
   availability as a convenience. The form's required fields depend on `resource.resource_type` —
   attendee count for a venue, destination and passengers for a vehicle.
2. On POST, the Django form validates field-level rules (times within the bookable window, duration
   or trip-length limit, attendee or passenger count against capacity, advance-booking limit,
   licence and road tax expiry for a vehicle).
3. Eligibility is checked: a vehicle booking requires `affiliation in (LECTURER, STAFF)`.
4. Inside `transaction.atomic()`, the view re-checks for conflicts with `select_for_update()` over
   the resource's overlapping bookings (see `booking-rules.md`).
5. The booking is saved with status `PENDING` — every resource requires approval (decision 4).
6. For a recurring request, every occurrence is expanded and checked in the same transaction, and
   any clashes are reported back rather than skipped.
7. An `AuditLog` row is written for administrator-initiated actions, including bookings created on
   behalf of another user.
8. A `BOOKING_SUBMITTED` row is written to `email_outbox` in the same transaction — never a direct
   `send_mail()` call, so a slow mail server cannot fail the booking.
9. The user is redirected to the confirmation page with the generated `booking_reference`.

Client-side validation is never trusted. Every rule is enforced on the server.

## Registration flow

There is no IIUM single sign-on (decision 24), so the system authenticates users itself.

1. The registration form requires name, an `@iium.edu.my` or `@live.iium.edu.my` address,
   matriculation or staff number, telephone, affiliation and a password.
2. The account is created with `email_verified = False` and cannot book anything.
3. A signed, time-limited verification link is emailed. Following it sets `email_verified = True`.
4. Driving licence details are captured later, on the first vehicle booking, not at registration —
   most users never need them.

Registration and password-reset endpoints are rate-limited. A public registration form on a public
domain will be probed.

## Frontend approach

Django templates plus Bootstrap 5, served from `static/` — **not from a CDN**, so the application
works on a restricted institutional network and does not break when a third party changes a URL.
Progressive enhancement only: pages work without JavaScript; JavaScript adds live availability
checks, filter behaviour and confirmation dialogues.

## Configuration

Environment-specific values (`SECRET_KEY`, database credentials, `ALLOWED_HOSTS`, media root, SMTP
credentials) come from environment variables, never from committed files.
`config/settings/production.py` sets `DEBUG = False`, secure cookie flags, HSTS and
`SECURE_SSL_REDIRECT`.

## Scheduled work

No message queue. Three cron entries calling management commands:

| Command | Frequency | Purpose |
| --- | --- | --- |
| `send_queued_email` | Every 5 minutes | Deliver `PENDING` rows from `email_outbox`, retry failures, prune sent rows older than 90 days |
| `complete_bookings` | Daily | Move `APPROVED` bookings whose `end_at` has passed to `COMPLETED` |
| `backup_database` | Daily | Dump the database, then copy the dump to external storage |

All three are idempotent. Retention cleanup is deliberately **not** scheduled — decision 20 and the data
protection rules require an administrator to review and confirm.

## Deployment

One Linux VPS is sufficient. Hosting and the domain are self-provided rather than supplied by IIUM
ITD (decisions 22 and 23), which has two consequences worth stating plainly:

- **There is a recurring cost.** The software is free; the server and domain are not.
- **Operations are this project's responsibility** — operating-system patching, firewall rules, TLS
  certificate renewal, and verifying that backups actually restore. No institutional IT department
  is doing these in the background.

Nginx serves `/static/` and `/media/` directly and proxies everything else to Gunicorn. Database
backups run from cron and are copied off the server. See `data-retention.md` for the backup schedule
and `security.md` for the hardening checklist.
