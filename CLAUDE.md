# CLAUDE.md — AIKOL Room and Vehicle Booking System

Persistent technical memory for developers and for Claude Code. This file describes the
**current intended** architecture, requirements and status — not obsolete plans.

> **Keep this current.** Whenever architecture, requirements, database design or major features
> change, update this file in the same change. If this file and the code disagree, that is a defect.

---

## 1. Project

A web-based **resource booking system** for the **Ahmad Ibrahim Kulliyyah of Laws (AIKOL)**,
**International Islamic University Malaysia (IIUM)**. It covers two kinds of bookable resource:

- **Venues** — moot court, seminar rooms, meeting rooms, lecture rooms, discussion rooms.
- **Vehicles** — Kulliyyah cars (other vehicle classes may follow; only cars in the first release).

Students, lecturers and staff check availability, submit booking requests and follow their status;
the Kulliyyah office approves, rejects and cancels bookings, issues and receives keys, and maintains
resources, users and reports.

### Guiding principle

> Use the simplest architecture that reliably supports the actual business requirements.

Do not introduce a framework, service, dependency or infrastructure component without a documented
reason. Prefer free and open-source software throughout. Avoid vendor lock-in. Another developer
must be able to take this over.

### Objectives

Centralise bookings of rooms and vehicles · real-time availability · simple submission ·
less administrative work · no double bookings · approval where required · authorised cancellation ·
reliable history · key custody recorded · better utilisation · management reporting ·
governance and audit · low cost · maintainable.

---

## 2. Current status

**Phases 1 to 8 are COMPLETE, and the system is LIVE on Google Cloud Run.**
**All 26 section 24 decisions have been answered by AIKOL** (see section 5).
The Django project exists, the database is built, authentication works, resources are browsable
and manageable, bookings can be submitted, decided and cancelled — single and recurring — and
key custody, user management, settings and the audit log are in place, and
bulk CSV import and export, reporting and retention are built, and the
**security review is done**. Production runs at the generated `*.run.app` hostname on Cloud Run
with Neon PostgreSQL and Cloudflare R2 — see `docs/technical/managed-cloud-deployment.md`.
Phase 9 (user acceptance testing) can begin: **email leaves the production outbox** (Gmail SMTP,
entered on the System screen on 21 September 2026, verified end to end with a password reset).
Two operational items remain open (section 5, *Still open*).

### Since the security review

- **Deployed.** A single immutable image (`Dockerfile`), a public Cloud Run service capped at one
  instance, a private IAM-authenticated maintenance service driven by Cloud Scheduler for the outbox,
  the `COMPLETED` transition and backups, and a migration-only Cloud Run Job. Every secret is read
  from Secret Manager; `deploy/cloud-run/deploy.ps1` refuses to run until all six exist. A
  `SecurityPolicyMiddleware` sets a deny-by-default Content-Security-Policy and a Permissions-Policy.
- **Redesigned.** The interface was audited end to end (`docs/ux-audit.md`) and brought onto the
  locked multi-page system in `design.md`, carried by `static/css/tokens.css` and `redesign.css`.
- **Self-drive is gone entirely.** Requesters never drive a Kulliyyah car, so the licence fields left
  the user model and the vehicle form. Anything that asks for a licence is a defect.
- Users edit their own profile; resource terminology is *Venue* and *Vehicle* throughout.
- A scripted **action matrix** (`tools/test_action_matrix.py`, `docs/technical/action-test-matrix.md`)
  drives every named route as every role.
- **A second factor for approvers and administrators.** An authenticator app (TOTP), enforced by
  middleware so no screen can forget: enrolment is forced at first sign-in, a code is required every
  session, ten single-use recovery codes are issued once, and an administrator can reset a
  colleague's device (never their own). `docs/technical/security.md` has the design. **373 tests.**
- **`prepare_uat`** resets production for acceptance testing: deletes every booking, series, key
  handover, archive row, the audit log and sent/failed email; deletes venues whose name or code
  contains "test"; adds three UAT venues (`UAT-VEN-01..03`) drawn with the `moot-court`,
  `seminar-a` and `meeting-a` placeholders. Users, settings, site content, terms, facilities and
  vehicles are untouched. Reports only unless `--confirm`; refuses once a UAT venue has a booking.
  Run it as a Cloud Run job after `backup_database`. **429 tests.**
- **Plain wording pass before UAT.** Interface copy was rewritten for a first-time user across
  templates, form hints and error messages: on/off settings are described as Yes/No, arithmetic
  asides are gone, and users are told to contact "the Admin". Setting descriptions live in
  `SystemSetting.DEFAULTS` and are copied into existing rows by a data migration
  (`administration.0007`), as `0005` did before it.
- **Signed R2 image URLs are reused** for most of their hour (`CappedR2Storage.url`, cached), so
  the browser caches uploaded images instead of re-fetching them on every page. The uploaded IIUM
  logo, identical to the static default, is cleared by `administration.0008`.
- **The collapsed rail is restored before first paint** by `static/js/nav-state.js`, loaded
  blocking in `<head>`; the `nav-collapsed` class now sits on `<html>`, not on `.docket-shell`.
  Restoring it from the deferred `chrome.js` animated the rail shut on every page load. Page
  transitions no longer morph the workspace box between pages of different heights.

The answers changed the scope materially. Vehicle booking, recurring bookings, key custody tracking,
a separate Approver role, self-registration, booking confirmation email and an administrator-managed
facility list were all added; several of them were previously listed as out of scope. Read section 5
before writing any code.

The prototype and the management report have both been brought into line with the answers.

### Delivered

| Deliverable | Location | Current against decisions? |
| --- | --- | --- |
| Management review report (HTML, printable to PDF) | `management-report/index.html` | Yes — section 24 now records AIKOL's answers |
| Interactive UI prototype, 19 screens | `prototype/` | Yes — venues, vehicles, keys, facilities, registration |
| Placeholder images (48 SVG) + generator | `prototype/assets/images/`, `tools/generate_placeholder_images.py` | Yes — 32 venue, 16 vehicle |
| Developer documentation | `docs/` | Yes |
| **Django project — models, auth, resources, bookings** | `aikol_booking/` | Yes |
| This file | `CLAUDE.md` | Yes |

### Built in Phase 3

- `config/settings/{base,development,production}.py`. Production refuses to start without its
  secrets; `manage.py check --deploy` is clean.
- **The custom user model landed in the first migration**, as required — `accounts.User`, email as
  the login field, `identification_number` unique and nullable, `role` and `affiliation` as separate
  fields.
- Every model in section 6, including `resources` with `Venue` and `Vehicle` on top of it,
  `academic_terms` with `term_breaks`, the `email_outbox`, and the append-only `audit_logs`.
- `bookings/0002_overlap_constraints.py` — the PostgreSQL exclusion constraints for overlapping
  bookings and overlapping terms, skipped on SQLite with the reason stated.
- `bookings/services.py` — the conflict rule, period validation and series expansion. One
  implementation for venues and vehicles alike.
- Self-registration with the IIUM-domain rule and the "not from IIUM" path, emailed verification,
  sign-in, password reset.
- Four management commands: `send_queued_email`, `complete_bookings`, `seed_settings`,
  `seed_facilities`. All idempotent.
- **89 tests, all passing**, including the whole mandatory conflict table run twice — once against a
  venue, once against a vehicle — and the multi-day overlap table.

### Built in Phase 8

- **Rate limiting** on registration, sign-in, verification and password reset — two buckets, per IP
  and per address. Production counts in the **database** cache, not local memory: a per-process
  counter would give an attacker one bucket per Gunicorn worker.
- **Registration no longer enumerates addresses.** A known address gets the same response as a new
  one and the existing account is emailed instead. This needed `validate_unique` overriding as well
  as the form message removed — Django's own model check was re-adding the oracle afterwards.
- A **smoke test over every URL**, and an **authorisation matrix** of every restricted screen
  against every role.
- `config/testrunner.py` clears the cache between tests, because the rate limiter counts somewhere
  Django's per-test rollback does not reach.
- **318 tests** (one expected skip), including deployment email-configuration coverage.

### Built in Phase 7

- **CSV import** with a preview that writes nothing: every failing row is reported with its line
  number and *every* reason, so a spreadsheet is corrected in one pass.
- **Streaming CSV export**, with facilities emitted in the same pipe-separated code format the
  import accepts. No password hash in any export; personal identifiers only in the user export.
- **The demand heatmap**, spreading each booking across the hours it occupies. Vehicles excluded —
  an overnight trip has no meaningful hour of day.
- **Retention**: preview, typed confirmation, export-and-verify, then delete in batches of 1,000.
  Permanent deletion with no copy is not offered on the screen.
- A **design audit** against the installed design skills fixed three real defects — see section 10.

### Built in Phase 6 and 6b

- **Key issue and return, recording four separate people**: who booked, who collected, who issued,
  and who received it back. The office screen lists keys out, overdue keys and those awaiting
  collection.
- **A key outstanding survives the booking reaching `COMPLETED`.** The two facts are tracked
  separately on purpose — a booking whose period has ended is exactly the case worth chasing.
- **Booking on behalf of a user** (decision 14), attributed to both: `user` is who it is for,
  `created_by` who submitted it, and the confirmation goes to the former. Eligibility to *drive* is
  judged against the person the booking is for, so an administrator cannot confer it on a student by
  filling the form in for them.
- Administration: overview, user management with activation, editable system settings, editable
  header/footer/login content, separate login and home photography, scheduled announcements, and a
  read-only audit log screen.
- **The user form has no password field**, deliberately. An administrator who can set someone
  else's password is a liability, and the reset flow already exists.

### Built in Phase 5 and 5b

- Availability per day, worked out **on the server**; the browser's check is a convenience on top.
- Booking submission for both resource kinds through one form: the fields differ, the period rules
  and conflict check do not.
- **Recurring bookings in two passes.** The first shows exactly what would be created and what would
  be left out, separated into *outside teaching* (the calendar working as intended) and *already
  reserved* (somebody else being there). Only then may the requester accept a partial series.
  Expansion is atomic: a failure partway leaves nothing, because half a timetable looks complete.
- Approval and rejection with a re-check under a row lock; series approval re-checks each occurrence
  separately and sends **one** summary email.
- Cancellation with a mandatory reason and the three-day cutoff, which approvers are not bound by.
- **Every booking email goes through the outbox**, written in the same transaction. A test rolls a
  booking back and asserts the message dies with it.

### Built in Phase 4

- **The confirmed stylesheet is ported**, not re-derived: `static/css/app.css` comes from
  `prototype/css/styles.css` with two changes — the login photograph moves under `static/`, and the
  prototype's demonstration ribbon is gone.
- **Amiri and IBM Plex Sans are vendored** as 30 WOFF2 subsets under `static/fonts/` (898 KB),
  declared in `static/css/fonts.css` with `unicode-range` preserved so a browser rendering Latin
  text never downloads the Arabic subset. Nothing loads from a CDN.
- Browsing: room list, vehicle list, resource detail. Filters and search run **in the query**, and
  pagination links carry the active filters.
- Management: venue, vehicle and facility screens, with the three-tab resource bar; image upload
  with server-side format sniffing; the two-gate delete; drag-and-keyboard facility reordering that
  posts the whole visible order for the server to rewrite as `1..n`.
- **128 tests, all passing.**

### Verified against PostgreSQL

The suite has now run against PostgreSQL 18 through `config.settings.postgres`: **341 tests, no
skips.** The concurrency test ran for the first time and passed — two simultaneous submissions for
one slot produce exactly one booking — and the exclusion constraint refused every overlapping row a
test tried to insert around the service layer. Two workflow tests had been relying on SQLite
letting that illegal row in; they now assert the constraint on PostgreSQL and the approval re-check
on SQLite. The SQLite run still reports one skip, the concurrency test, as intended.

### Not started

Phase 9, user acceptance testing. Training, under Phase 10.

### Next step

**Phase 9 with the office.** Email is delivered, so a new user can finish registering. The first
end-to-end test exposed that the password reset was bypassing the outbox (fixed the same day); expect
acceptance testing to find more of that kind.

---

## 3. Repository layout

```
.
├── CLAUDE.md
├── Section 24.docx             # AIKOL's answers to the 26 decisions — source of truth for
│                               # section 5. Held locally only; excluded from the public
│                               # repository because it is AIKOL's internal material.
├── management-report/          # Phase 1 deliverable for management (HTML, not Markdown)
│   ├── index.html              # 25 numbered sections, auto-numbered by report.js
│   ├── css/report.css          # includes the print stylesheet
│   ├── js/report.js            # charts, contents, scroll spy, print
│   └── assets/images/
├── prototype/                  # Phase 1 interactive UI prototype (no backend)
│   ├── index.html login.html dashboard.html venues.html venue-details.html
│   ├── booking.html my-bookings.html admin-dashboard.html admin-bookings.html
│   ├── admin-venues.html admin-users.html data-management.html
│   ├── css/styles.css
│   ├── js/prototype.js         # sample data + shared behaviour, global `AIKOL`
│   └── assets/images/
├── design.md                   # the locked visual system — current source of truth for the UI
├── PRODUCT.md                  # product summary consumed by the design tooling
├── Dockerfile                  # the production image; collectstatic runs under settings/build.py
├── cloudbuild.yaml             # repository-triggered image builds
├── compose.production.yml      # the earlier self-hosted path (Caddy + Gunicorn); superseded by Cloud Run
├── deploy/
│   ├── Caddyfile               # self-hosted path only
│   └── cloud-run/              # deploy.ps1, bootstrap-admin.ps1, reveal-admin-password.ps1
├── docs/
│   ├── README.md
│   ├── ux-audit.md             # the end-to-end interface audit that drove the redesign
│   ├── user-guide.md           # first-time guide for requesters
│   ├── admin-guide.md          # guide for the office: approvers and administrators
│   ├── images/                 # screenshots in the guides; retake when a pictured screen changes
│   ├── uat-test-script.md      # the acceptance test script the office works through
│   └── technical/              # architecture, schema, booking rules, retention, security,
│                               # testing, bulk import, prototype guide, managed-cloud
│                               # deployment, SMTP setup, custom domain, action test matrix
└── tools/
    ├── generate_placeholder_images.py
    └── test_action_matrix.py   # drives every named route as every role
```

The Django project is in `aikol_booking/` at the repository root, laid out as
`docs/technical/architecture.md` specifies: `config/settings/` split four ways (`base`,
`development`, `production`, and `build` for image builds that must need no secret; `postgres`
layers a `DATABASE_URL` over development for the PostgreSQL test run), `apps/` holding the eight
modules, plus `templates/`, `static/`, `media/` and `requirements.txt`. The virtual environment
lives in `.venv/` and is not committed. Migrations **are** committed.

The prototype covers venues only; the vehicle screens exist in the Django application, not in the
prototype.

---

## 4. Technology stack (decided)

| Layer | Choice | Note |
| --- | --- | --- |
| Backend | **Python 3.11+ / Django 5.x LTS** | Built-in auth, ORM, migrations, admin, security |
| Frontend | **Django templates + Bootstrap 5** | Vendored in `static/`, **not** a CDN |
| Icons | **Bootstrap Icons** | Vendored |
| Typefaces | **Amiri** (headings) + **IBM Plex Sans** (UI) | Required by the confirmed design. **Must be vendored as WOFF2 under `static/`** — see section 14 |
| Database (dev) | **SQLite** | Zero setup |
| Database (prod) | **PostgreSQL 15+** | Required — the overlap exclusion constraint needs it |
| Authentication | **Django's own auth. No IIUM SSO** | Confirmed decision, not a placeholder — see section 5 |
| Email | **Administrator-configured SMTP, sent from a database outbox on a schedule** | Password encrypted at rest; account and booking confirmations. Configured in production (Gmail, App Password) |
| Scheduled jobs | **Cloud Scheduler calling a private, IAM-authenticated maintenance service** (`config/maintenance.py`) | Outbox drain, `COMPLETED` transition, backups. A request-billed service, not a Cloud Run Job — Jobs bill a one-minute minimum per run. No Celery |
| Charts (app) | Plain HTML/CSS; **Chart.js** only if a chart genuinely needs it | Vendored if adopted |
| Web server | **Gunicorn + WhiteNoise in one container** | TLS is terminated by Cloud Run; the Caddy/Compose files remain for a self-hosted fallback |
| Hosting | **Google Cloud Run (max 1 instance, scale to zero); Neon PostgreSQL; Cloudflare R2 (private buckets, signed URLs); Secret Manager** | Live. Oracle's free VM was tried and rejected by Oracle's own screening. Google requires an active billing account; the free allowance is not a hard cap, so instance count and spend alerts are the controls |
| Domain | **The generated `*.run.app` hostname**, for now | A `.my` domain was researched and deliberately not bought pending a decision on institutional ownership |
| Version control | **Git** | |
| Testing | Django test framework | `manage.py test`. 373 tests. The PostgreSQL run uses `config.settings.postgres` |
| Image handling | **Pillow** | Required by Django's `ImageField`. Not optional — resource photographs are a confirmed requirement |
| PostgreSQL driver | **psycopg 3** | Production, and the PostgreSQL test run. Installed in development so `check --deploy` can run |
| Object storage | **django-storages[s3]** | R2 is S3-compatible; media and backups in separate buckets with application-enforced soft limits |
| Connection URL | **dj-database-url** | Parses `DATABASE_URL` instead of hand-splitting it |
| Credential encryption | **cryptography / Fernet** | Protects the SMTP password stored from the administrator screen, and the one-time administrator password handoff |
| Second factor | **TOTP on the standard library** (`apps/accounts/mfa.py`) + **qrcode** for the enrolment QR | RFC 6238 is thirty lines and is tested against the RFC's vectors; `qrcode` is pure Python and renders inline SVG. No authentication library |
| Cost | **RM 0 within provider free allowances**, unproven | Spend-cap budget set. No claim of staying free is made until a monitored pilot provides evidence |

### Explicitly rejected (do not add without a documented reason)

React / Vue / Next.js · microservices · Celery or any message queue · paid cloud services ·
paid image hosting · CDN-loaded assets · any AI feature. The business problem is scheduling and
record keeping; none of these solve it.

---

## 5. Requirements

### Confirmed (from the project brief — treat as settled)

- Browse venues and vehicles, view details and photographs, check availability.
- Submit, view and cancel own bookings; view own history.
- Administrators manage users, resources, images and bookings; approve, reject and cancel.
- **Double bookings must be prevented.**
- Booking history retained and reportable; cancellation does not delete records.
- Search, filtering, pagination and server-side querying on every list screen.
- Bulk CSV import and export; configurable retention; audit log.
- Low cost, simple, maintainable, secure, responsive.

### Confirmed by AIKOL — answers to section 24

Answered by **the Kulliyyah system administrator**, who will also
supply the resource list, rules and photographs. Source: `Section 24.docx` in the repository root.
These are **settled decisions**, not assumptions — implement them as stated.

**Access and eligibility**

| # | Decision |
| --- | --- |
| 1 | Anyone with an IIUM matriculation number or staff number may use the system |
| 2 | Students may book venues independently; approval is granted on the strength of the reason and availability |
| 3 | Students may book **all** venues |
| 4 | **Every venue requires administrator approval.** No venue is auto-confirmed |
| 5 | **A separate Approver role is required** — for an Administrative Assistant, Executive Officer or Deputy Director to decide bookings when the main approver is away |
| 6 | One level of approval is sufficient |

**Booking rules**

| # | Decision |
| --- | --- |
| 7 | Bookings may be made up to **3 months (90 days)** in advance |
| 8 | Maximum **9 hours** for a single booking; a longer occupation requires a second booking |
| 9 | Bookable window **08:00–22:00** |
| 10 | Weekend bookings are permitted |
| 11 | Public holiday and semester break bookings are permitted |
| 12 | A user may cancel their **own** booking freely, up to **3 days before the booking date**, with a reason. Only administrators and approvers may *approve* |
| 13 | Cancellation notice: **3 days**, with a reasonable excuse |
| 14 | Administrators **may** create bookings on behalf of users |
| 15 | **Recurring bookings are required in the first release** — needed to fill a whole semester's schedule |

**Resource access and information**

| # | Decision |
| --- | --- |
| 16 | Keys and access cards are held by the system administrator personally; there is no maintenance partner |
| 17 | **Key collection and return must be recorded in the system** |
| 18 | Store per user: name, matriculation / staff number, telephone number. Per booking: remarks / purpose, key time out, key time returned |

**Records and data**

| # | Decision |
| --- | --- |
| 19 | Retain booking records **7 years**, for audit |
| 20 | Records past that period are **exported**, not archived in place and not silently deleted |
| 21 | A database backup is required before any bulk deletion; backups go to **external storage** |

**Infrastructure and ownership**

| # | Decision |
| --- | --- |
| 22–23 | **Not IIUM ITD.** Hosting and domain are self-provided |
| 24 | **No IIUM authentication integration.** The system implements its own, using Django's auth |
| 25 | System administrator: the Kulliyyah office |
| 26 | Resource list, rules and photographs: supplied by the Kulliyyah office |

### Confirmed in follow-up — vehicles and registration

Vehicle booking was added after section 24 was answered. Section 24 says nothing about vehicles;
these decisions are the authority for them.

| Topic | Decision |
| --- | --- |
| Vehicle scope | **Cars only** in the first release. The model must not make other vehicle classes hard to add |
| Who may book a vehicle | **Anyone may book, students included.** Requesters do not drive Kulliyyah vehicles; every trip uses the VMU/STADD route |
| Trip length | **Multi-day trips are allowed.** A vehicle may be collected one day and returned another; a system setting caps the maximum trip length |
| Driver | **No self-drive.** A driver is supplied by the Vehicle Management Unit and assigned by an administrator after the ordinary booking decision |
| VMU driver route | Requested from the Vehicle Management Unit through **STADD**, and needs **Kulliyyah management approval** to use a Kulliyyah car — a second approval on top of the booking approval. The booking form states this so the requester is not surprised |
| Vehicle key record | Held by the system administrator personally. Per vehicle booking record: **date out and date in, driver name, contact number, staff number, location from and location to, purpose** |
| Vehicle approval | Every vehicle booking requires approval, as with venues |
| Registration | **Self-registration**, restricted to `@iium.edu.my` and `@live.iium.edu.my` addresses, confirmed by a verification email. Matriculation or staff number is captured at registration |
| Matriculation number | Collected for documentation and reporting. It is **not** the login credential — email remains the login field |
| **Booking confirmation email** | Confirmations are sent by email on submission, approval, rejection and cancellation. Transactional, so there is no opt-out in the first release |
| **Administrator-managed facilities** | Administrators create, rename and deactivate facilities themselves. The list is no longer fixed in code, which is why facilities become a table |

### Consequences that are easy to miss

- **Email sending is in the first release, for accounts *and* bookings.** The old assumption "no
  email notification in the first release" is void in both halves. Every booking status change now
  emails the requester, which makes the mail server a dependency of ordinary operation rather than
  of signup alone — hence the outbox table in section 6.
- **Total cost is no longer RM 0.** Software remains free, but self-provided hosting and a domain are
  a recurring expense. Sections 15 and 16 of the management report now say so.
- **Decision 12 does not create a cancellation-approval workflow.** Users cancel their own bookings
  outright. The sentence "approval needs to be approved by Admin" in the source document refers to
  booking approval, which was clarified directly with AIKOL.
- **Decision 4 makes `approval_required = false` unused** in the first release. Keep the field —
  it costs nothing and AIKOL may relax the rule — but no resource ships with it set.
- **Vehicle eligibility was reversed after the first draft.** An earlier note in this file said
  students could not request a car at all. That is wrong and has been corrected above: students may
  book, they simply may not drive. Anything written against the old rule — a 403 for students on
  the vehicle form, a hidden vehicles tab — is a defect, not a feature.
- **A VMU booking carries two approvals**, not one: the ordinary booking approval by the Kulliyyah
  office, and Kulliyyah management approval to use the car with a VMU driver. The system records
  both; it does not merge them.

### Still open

The system is deployed and email is delivered (Gmail SMTP through the administrator screen; a
Google App Password, port 587 with TLS). Two items require the Kulliyyah office or the AIKOL account
owner:

1. **Decide on a domain.** Production answers only at the generated `*.run.app` address. A `.my`
   registration is a recurring fee and raises the question of institutional versus personal
   ownership; neither has been decided. The procedure, once decided, is
   `docs/technical/custom-domain.md`; `deploy.ps1 -PublicDomain` carries the name.
2. **Authenticator enrolment by every approver and administrator** at their next sign-in. The
   system forces it; the office should expect the step and keep the recovery codes it prints
   somewhere that is not the phone.

The free-tier cost analysis is an estimate: it needs real booking volume and a load test before
"RM 0" can be stated as fact.

**Never present a decision as established AIKOL process unless it appears above** — in code
comments, in the report, or in conversation with the user.

---

## 6. Database

Full detail in `docs/technical/database-schema.md`. Summary:

`users` · `resources` · `venues` · `vehicles` · `resource_images` · `bookings` ·
`booking_series` · `key_handovers` · `booking_archive` · `audit_logs` · `system_settings` ·
`site_content` · `announcements` · `totp_devices` · `recovery_codes` · `email_wording`

Key decisions:

- **Custom user model** (`accounts.User`) with `email` as the login field, plus
  `identification_number` (matriculation or staff number, unique) and `phone`. It was set up in the
  very first migration, as it had to be. The driving licence fields it once carried were removed
  with self-drive: nobody who books a car drives it.
- **One `resources` table, extended by `venues` and `vehicles`.** A venue and a car differ in their
  attributes but are identical in what matters: a thing reserved for a period, requiring approval,
  with keys handed over, that must never be double-booked. `bookings.resource` points at
  `resources`, so there is **one** conflict rule, **one** exclusion constraint and **one** set of
  conflict tests. Two parallel booking tables would mean two implementations of the system's core
  promise, and they would drift.
- **Bookings use `start_at` / `end_at` timestamps**, not `booking_date` + `start_time` / `end_time`.
  Vehicles can be out overnight; venues cannot. Timestamps serve both, and they make the exclusion
  constraint simpler and more obviously correct than a date-plus-time reconstruction.
- `bookings.user`, `bookings.resource` and `bookings.created_by` use `on_delete=PROTECT`. Users and
  resources are **deactivated, never deleted**, while history references them.
- `bookings.created_by` is distinct from `bookings.user` so that a booking made by an administrator
  on someone's behalf (decision 14) is honestly attributed to both.
- **Facilities are a table, joined to resources many-to-many.** They were a JSON field while the
  list was a fixed set of nine values defined in code. Administrators can now create facilities, and
  a facility an administrator creates needs a stored display name — which is an attribute of its
  own, the exact condition this file already set for normalising. See section 13.
- **Email leaves through an `email_outbox` table**, written in the same transaction as the action
  that caused it and sent by a cron-driven management command. A booking must never fail because a
  mail server is slow, and a semester-long series must never block a request behind 26 SMTP
  round-trips. This is not a message queue and does not reopen that decision. The singleton
  `email_configuration` row holds administrator-editable SMTP settings; its password is encrypted
  with an environment-held Fernet key and never appears in the form or audit log.
- **The academic calendar is several terms, not one.** `academic_terms` holds a row per semester
  with `term_breaks` beneath it, and terms **must not overlap** — "which semester is this date in?"
  has to have exactly one answer, or the recurrence generator's behaviour is arbitrary. Enforce it
  with a `daterange` exclusion constraint, the same mechanism the booking rule uses. A term carries
  no foreign key from bookings, so deleting one cancels nothing.
- `booking_series` holds the recurrence definition; every occurrence is a real `bookings` row
  pointing back at it. Do not compute occurrences on the fly — a booking that does not exist as a row
  cannot participate in the exclusion constraint, and the whole no-double-booking guarantee collapses.
- `key_handovers` records issue and return per booking (decision 17), with who issued, who received
  and the timestamps.
- `booking_archive` stores denormalised copies (user email/name, resource code/name) and has no
  foreign keys, so it survives changes to the live tables.
- `audit_logs` is append-only. Application code never edits or deletes it.
- Business rules live in `system_settings`, not in the code.
- Public identity and introductory copy live in the single `site_content` row. The AIKOL and IIUM
  logos, login image and home image are independent uploads. `announcements` stores active/scheduled
  notices and keeps deactivated rows rather than deleting them.

### Confirmed setting values

| Key | Value | From |
| --- | --- | --- |
| `advance_booking_limit` | 90 days | Decision 7 |
| `maximum_booking_duration` | 540 min (9 h) | Decision 8 |
| `bookable_window_start` / `_end` | 08:00 / 22:00 | Decision 9 |
| `cancellation_cutoff` | 72 hours | Decisions 12, 13 |
| `cancellation_reason_required` | true | Follow-up decision |
| `allow_user_cancel_approved` | true | Decision 12 |
| `booking_retention_period` | 7 years | Decision 19 |
| `retention_disposal_action` | `EXPORT` | Decision 20 |
| `maximum_vehicle_trip_days` | to be set by AIKOL; default 7 | Follow-up decision |

### Indexes (add these, and no more without a reason)

`(resource_id, start_at)` · `(user_id, start_at DESC)` · `(status, start_at)` · `(start_at)` ·
`(series_id)` · unique `booking_reference` · unique `users.email` ·
unique `users.identification_number` · unique `resources.code` ·
unique `vehicles.registration_number` · unique `facilities.code` ·
`(resource_id, facility_id)` unique on `resource_facilities` · `(status, created_at)` on `email_outbox` ·
`(entity_type, entity_id)` and `(created_at DESC)` on `audit_logs`.

Plus the PostgreSQL exclusion constraint that makes overlapping active bookings impossible at the
database level.

---

## 7. The core business rule — no double bookings

For a resource — venue or vehicle alike — a new booking conflicts when:

```
new_start < existing_end  AND  new_end > existing_start
```

counting **only** existing bookings with status `PENDING` or `APPROVED`.
`REJECTED` and `CANCELLED` bookings do not reserve the resource. Adjacent bookings
(10:00–12:00 then 12:00–14:00) do **not** conflict — the comparison is strict.

Because `start_at` and `end_at` are timestamps, this one rule covers a two-hour seminar room slot
and a three-day outstation car trip without a special case.

Enforced in three places: the browser (convenience only, never trusted), the server (on submission
*and* again on approval, inside `transaction.atomic()` with `select_for_update()`), and the database
(exclusion constraint).

Status lifecycle: `PENDING → APPROVED | REJECTED`, `APPROVED → COMPLETED | CANCELLED`.
Every resource requires approval (decision 4), so in practice every booking starts `PENDING`.

**Recurring bookings** (decision 15) are expanded to individual rows at submission time, each checked
against the same rule. If some occurrences clash, the clashing ones are reported and the user decides
whether to submit the remainder — never silently skip an occurrence, and never abandon a whole
semester's series because week 7 is taken.

The mandatory conflict tests are listed in `docs/technical/testing-strategy.md`. Do not consider the
booking feature complete without them.

---

## 8. Data protection rules (non-negotiable)

- Cancelling a booking sets `status = CANCELLED`. **It never deletes the row.**
- Deactivating a user or resource sets a status. **It never deletes the row.**
- A **resource may be deleted, but only through two gates.** It must be deactivated first — a matter of
  intent, so that nothing leaves the system in one click from a list — and it must have **no booking
  referring to it**, which `on_delete=PROTECT` enforces in the database rather than in the view.
  Deletion is therefore for one case: a venue or vehicle entered in error that nobody ever booked.
  A resource that has been used is deactivated and keeps its history, permanently. Offer the action
  in the interface, refuse it in the database, and say which of the two gates stopped it.
- Retention is **7 years** (decision 19). It makes old records *eligible* for cleanup; an
  administrator must review and confirm.
- **Export is the default disposal action** (decision 20): rows are written to CSV outside the web
  root and the copy is verified before anything is removed. Permanent deletion without an export is
  restricted and requires a typed confirmation naming the record count.
- A backup is taken before any bulk deletion and before any migration. Backups are copied to
  **external storage** (decision 21); a backup that exists only on the application server is not a
  backup.
- Deletion runs in batches of 1,000 inside transactions, exporting before deleting.
- The full database reset is for development and migration only: highest administrator level,
  disabled by default in production settings, requires typing `DELETE ALL DATA`, requires a backup,
  written to the audit log.
- Telephone numbers and matriculation or staff numbers are personal data. They appear in exports
  only where the export's purpose requires them, and never in the audit log's free-text description.

---

## 9. Security requirements

**Rate limiting** on every public authentication endpoint, in two buckets — per IP and per
address — so neither one machine trying many accounts nor many machines trying one account runs
unchecked. Production counts in the database cache rather than local memory, because Gunicorn's
worker processes would otherwise each hold their own counter and multiply every limit silently.

**Registration does not reveal whether an address is already registered.** It returns the same
response either way and emails the existing account instead. A matriculation number collision *is*
reported, because a number cannot be probed for a list of people the way an address can, and a
silent merge would corrupt the booking record.

**Approvers and administrators present a second factor** — a code from an authenticator app —
at every sign-in, enforced by `MfaRequiredMiddleware` for every request rather than by a decorator a
screen could omit. Enrolment is forced the first time; recovery codes are single-use and hashed; an
administrator may reset a colleague's authenticator but never their own; `manage.py reset_mfa` exists
for the last administrator. Ordinary users are not asked: their authority is over their own bookings.

Django's built-in authentication with hashed passwords — never a hand-written scheme, never plain
text. The system provides its own authentication; there is no IIUM SSO and none is planned
(decision 24), so account security is entirely this system's responsibility.

**Self-registration** is open but constrained: the email address must end in `@iium.edu.my` or
`@live.iium.edu.my`, the address must be confirmed by a verification link before the account can
book anything, and a matriculation or staff number is required and unique. Rate-limit registration
and password-reset requests — a public registration form on a public domain will be probed.

Role-based authorisation checked in every view (403, not a hidden menu item), across three roles:
standard user, **Approver** (decides bookings only), and Administrator. Vehicle booking is open to
every verified user, students included (section 5) — an earlier version of this sentence said
otherwise and was wrong. Ownership checked on the object, never inferred from the URL. CSRF on every form. Template
auto-escaping. ORM-only database access. All validation server-side. Uploads: images only, format
sniffed, 5 MB limit, renamed on save, stored outside the code path. HTTPS enforced; secure, HttpOnly
session cookies. `DEBUG = False` and `ALLOWED_HOSTS` set in production. Secrets from environment
variables. Run `manage.py check --deploy` before every deployment.

Because hosting is self-provided rather than managed by IIUM ITD, operating-system patching,
firewall rules, TLS certificate renewal and backup verification are all this project's
responsibility. Document them; do not assume someone else is doing them.

Full detail: `docs/technical/security.md`.

---

## 10. Coding standards

- PEP 8; `black` formatting; 100-character lines.
- Fat models and services, thin views. Business rules belong in the model layer or a service
  function, never in a template.
- Class-based views where they fit; function views where they read better. Consistency within an app
  matters more than the choice.
- Every list view paginates and filters **in the query**. Never load a full table to render a page.
- Use `select_related` / `prefetch_related` for related objects; watch for N+1 queries.
- Migrations are committed. Never edit an applied migration.
- Comments explain *why*, not *what*. Match the density of the surrounding code.
- No new dependency without a documented reason in this file.

### UI standards

- Semantic HTML, `<label>` for every input, `aria-current` for navigation state, alt text on every
  image, visible focus, keyboard-operable controls, contrast sufficient for body text.
- Responsive from 360 px upwards; one responsive site, not a separate mobile application.
- Institutional and restrained: no gratuitous animation, gradients or decoration.
- **The visual design is confirmed**, not a placeholder. AIKOL supplied it as
  `design/AIKOL Booking 1a.dc.html`; `prototype/css/styles.css` implements it and is the reference
  for the Django templates. Values are lifted from that file — do not re-derive or round them.
- Palette: green `#14675b` with gold `#d99b28` on warm paper `#f7f4ed`; panels `#fffdf8`; rules
  `#ded4bd`. Type: **Amiri** for headings and resource names, **IBM Plex Sans** for everything else.
  Radii 3–5 px; status pills at 10 px.
- The identity is carried by paired wordmarks (**AIKOL first, IIUM second**), the Arabic greeting,
  Amiri headings, warm paper, green ink and restrained gold rules. Photography uses rectangular
  frames. There is deliberately no other ornament: no crescents, mosque silhouettes or
  Arabic-styled Latin type.
- **Interaction states are part of the design, not decoration.** Every button has a `:active`
  press state; focus rings use `:focus-visible` so they are shown to keyboard users and not to
  mouse users; transitions name the property they animate and last 90–140 ms; a
  `prefers-reduced-motion` block turns all of it off. Motion here is the least that still confirms
  an action registered — this is an institutional booking system, not a marketing page.
- **Django renders form controls with no class of their own**, and this stylesheet styles them by
  class. `config/forms.py` supplies `StyledFormMixin`, which every form uses. Without it the
  stylesheet loads and does nothing for any control on any page.
- `design.md` is the current visual source of truth. `static/css/app.css` retains the prototype's
  component foundation; `static/css/tokens.css` and `static/css/redesign.css` apply the locked
  multi-page system. New screens use those tokens and established component classes rather than
  adding page-local colours, fonts or shape rules.
- **An inline `style=""` attribute does nothing.** The Content-Security-Policy is `style-src 'self'`,
  so the browser drops every one, silently. A margin written that way is no margin; a bar width
  written that way is a bar with no width — which is exactly how sixty of them shipped. Use a class
  (`.mt-sm`, `.grid-top`, `.stack`, `.plain-list`…) and, for a size that comes from data, a
  `data-width` / `data-height` / `data-left` attribute that `chrome.js` applies. The smoke test
  fails on any `style="` in a rendered page.
- **Blocks that follow one another on a page are spaced by the flow rule** (`.main > * + *`), not
  by per-element margins. Containers never sit flush; no border is hidden under the block above.
- **Headings and tab labels are title case in the markup.** The old `text-transform: capitalize`
  is gone: it capitalised every word, including "And" and "Of".
- **Interface copy says the one thing the person needs.** No rationale, no engineering commentary,
  no reassurance about what the code does internally — that belongs in this file or in `docs/`.
- **Visible text uses ordinary punctuation.** No em or en dashes and no middle dots in anything a
  person reads on screen or in an email: a comma, a colon, a full stop, or the word "to" for a
  range ("09:00 to 11:00"). Dashes in code comments and in this file are fine. The default
  `SiteContent.subtitle` and the seeded office hours follow the same rule (migration
  `administration.0004`).
- **No eyebrow labels.** Nothing sits above a heading in small tracked capitals. A booking reference
  is a heading in its own right (`bookings/detail.html`) or a plain monospace line in a docket row;
  a resource code is not shown to a requester at all. `dt`, footer headings, search-bar keys and the
  like are sentence case with normal letter-spacing; status stamps and badges are the one place
  capitals remain.
- **On/off settings on administrator screens are a Yes/No choice, not a tick box.**
  `config.forms.yes_no_field` renders a boolean model field as a two-option drop-down and stores
  the same boolean; the SMTP encryption is one choice (STARTTLS, SSL, None) written back to
  `use_tls`/`use_ssl`. A tick box remains only where it is a declaration or a selection: the
  "not from IIUM" statement, partial-series consent, weekday pickers, facility grids.
- **Staff have one rail, not two views.** A person who approves bookings also makes them, so the
  requester's entries sit above a rule and the Kulliyyah's work below it. There is no User View /
  Administrator View switch, and no heading over either group: the rule is the separation. `shell_nav` distinguishes
  `home` (`/`) from `overview` (`/manage/`), and a resource page resolves to `venues` or
  `vehicles` by looking the resource up, because the path does not say which kind it is.
- **A long form saves from every section.** Someone editing the first section should not have to
  discover a button below the fold; each section's Save submits the whole form, and there is no
  separate bar at the foot repeating it.
- **Image fields use `config.forms.ImageInput`**, which shows the current image with a labelled
  "remove on save" choice instead of Django's bare "Clear" box. `FORM_RENDERER` is
  `TemplatesSetting` so widget templates live in `templates/widgets/`.
- **Accounts and academic calendars can be deleted through the same two gates as a resource**
  (retired first; no booking history, which PROTECT enforces). A person with history is retired,
  never deleted; a calendar carries no booking and may go at any time.
- **Email wording belongs to the office.** Every email's default subject and body live in
  `apps/notifications/wording.py` as `EMAILS`, with fill-in fields in braces; an edit from System,
  Emails is an `EmailWording` row, and deleting the row restores the default. Code decides when an
  email goes and what each field contains, so an edit cannot add personal data the code does not
  supply. Fields are filled by one regex pass, never `str.format` (no attribute access, no
  re-expansion of braces inside a value). Emails a person must act on keep their field: `{link}`
  for confirmation and reset, `{reason}` for a rejection. Send through `wording.send`, never by
  composing a body inline.
- **Counts are a ruled figures strip, not a row of cards.** `.grid-4 > .stat` and `.booking-stats`
  render as one strip with hairlines between figures (`redesign.css`, *Figures*); do not put the
  card border back or add a fifth identical box.
- **Motion has one curve and three durations**, all tokens in `redesign.css`; see `design.md`,
  *Motion*. Never add a second entrance to something that already arrives with the page.
- **A `{# #}` comment in a Django template is SINGLE-LINE ONLY.** A multi-line one is not a comment
  at all — it renders verbatim on the page. Use `{% comment %}…{% endcomment %}` for anything longer
  than a line. Thirteen of these shipped before anyone looked at the site in a browser.
- **Placeholder artwork comes from `static/images/placeholders/`**, the prototype's own drawings,
  chosen by `Resource.image_slug`. They are served as static files and never uploaded, so the rule
  that user-supplied SVG is refused is untouched. A resource with a real photograph ignores them.
- The real AIKOL wordmark and the supplied IIUM wordmark are used together. Administrators may
  replace either through Site content; static copies remain as safe defaults.

---

## 11. First release (MVP)

**In:** self-registration with IIUM email verification · authentication and password reset ·
three roles (user, approver, administrator) · user management with activation/deactivation ·
venue management with images · **vehicle (car) management with images** ·
**administrator-managed facility list** · **editable identity, page photography, login copy and announcements** ·
**booking confirmation email** · resource browsing,
filtering and details · availability display · booking submission for venues and vehicles ·
**multi-day vehicle bookings** · **VMU-driver workflow with a separate management decision** · **recurring bookings** · conflict prevention with tests ·
approval and rejection with reasons · **booking on behalf of a user** · cancellation with a
mandatory reason and a 3-day cutoff · **key issue and return recording** · booking history with
search, filter and pagination · dashboard and basic reporting · CSV import and export · audit log ·
configurable retention with export · documented backup procedure to external storage.

**Out (later, and additive — none requires an architecture change):**
IIUM single sign-on (explicitly not planned) ·
calendar integration · QR check-in or room access · equipment tracking beyond keys ·
vehicle classes other than cars · fuel and maintenance scheduling · mobile application ·
advanced analytics · any AI feature.

---

## 12. Roadmap

| Phase | Work | Status |
| --- | --- | --- |
| 1 | Discovery and management review | **Complete** |
| 2 | UI prototype and requirement confirmation | **Complete**; decisions received and folded into the prototype and report |
| 3 | Database, self-registration and authentication | **Complete** |
| 4 | Resource management (venues and vehicles) | **Complete** |
| 5 | Booking system and conflict prevention | **Complete** |
| 5b | Recurring bookings | **Complete** |
| 6 | Administrative features, approver role, booking on behalf | **Complete** |
| 6b | Key issue and return recording | **Complete** |
| 7 | Bulk data, reporting and retention | **Complete** |
| 8 | Testing and security review | **Complete** — except the PostgreSQL run |
| 9 | User acceptance testing | **Next.** Email is delivered; nothing blocks it |
| 10 | Deployment and training | **Deployed** to Cloud Run with scheduler, backups and spend alerts; SMTP configured. Outstanding: domain decision, training |

Phases 5b and 6b are numbered separately because they were added after the original plan and carry
schedule cost that the original estimate did not include. Recurring bookings in particular are not a
small feature: series definition, per-occurrence conflict checking, partial-failure handling, and
series-level approve and cancel.

---

## 13. Architectural decisions and why

| Decision | Reason |
| --- | --- |
| Modular monolith, not microservices | The modules share data and users. Services would add network failure modes for scaling this system will never need. |
| Django templates, not a JavaScript frontend | The interface is forms and tables. A second application doubles the code and the deployment for no benefit. |
| PostgreSQL required in production | The exclusion constraint that guarantees no overlapping bookings needs it. SQLite is development-only. |
| One `resources` table for venues and vehicles | The core promise is "no double bookings". Implementing and testing that rule once, rather than once per resource kind, is what keeps the promise true as the system grows. |
| Timestamps, not date plus time | Vehicles can be out overnight. One representation serves both resource kinds and makes the exclusion constraint simpler. |
| Recurrence expanded into real rows | An occurrence that is not a row cannot be covered by the exclusion constraint. Computing occurrences on the fly would silently defeat the database guarantee. |
| No CDN — everything vendored | Works on a restricted institutional network and does not break when a third party changes a URL. |
| Charts in HTML/CSS, not Chart.js (Phase 1) | The charts needed are bars. Chart.js remains available at no cost if a chart later justifies it. |
| Facilities normalised into a table | The original rule was "normalise when a facility needs attributes of its own". Letting administrators create facilities means each one needs a stored name, so the condition is met. Following the rule, not overriding it. |
| Email through a database outbox, still no queue | Solves latency and retry with one table and a cron entry already in the design. Celery would solve the same problem and add a broker to operate. |
| Deactivate, never delete *once used* | Booking history must stay complete for audit and reporting. An unused record entered in error is not history, so it may be deleted — after being deactivated first, so the removal is deliberate. |
| Export as the default disposal | Decision 20. Institutional data leaves the live database only as a verified file. |
| Business rules in `system_settings` | So that AIKOL can change a limit without a code release; the confirmed values are defaults, not constants. |
| Own authentication, no SSO | Decision 24. Also removes a dependency on ITD, who have not committed to hosting either. |
| Email in the MVP after all | Self-registration cannot verify an IIUM affiliation without it, and one administrator cannot create accounts by hand for a whole Kulliyyah. |
| Three roles now | Decision 5 requires an approver who is not a full administrator. Adding it now is cheaper than retrofitting permission checks. |
| No message queue for imports or recurrence | Not justified until measurement shows the work is too slow in a request. Expanding a semester of weekly bookings is a few hundred rows. |
| TOTP before passkeys for the second factor | Works on any phone the office already has, needs no script in the browser, and has a recovery path a person can hold in their hand. Passkeys are stronger and can be added on top; nothing in the TOTP design has to be undone for them. |
| The second factor is a middleware, not a decorator | The role decorators are repeated in seven modules. A screen that forgot one would also forget the second factor; a middleware has nothing to forget, and covers Django's own admin. |

---

## 14. Working conventions for this repository

- **The management-facing document is HTML, never Markdown.** Markdown is for `docs/` only.
- Sample and demonstration data must be obviously fictional (`@demo.aikol.test`, invented names) and
  labelled as such wherever it appears.
- Every chart or figure not derived from real AIKOL measurement is labelled **Illustrative data**.
  Never present an invented number as an AIKOL measurement.
- `management-report/js/report.js` numbers sections automatically from document order — reordering
  sections renumbers everything, so re-check in-text cross-references afterwards.
- Placeholder venue image slugs must not end in a digit; variants are suffixed `-v2`, `-v3`, `-v4`.
  The same convention applies to vehicle images when they are generated.
- `Section 24.docx` is AIKOL's own words and is **never edited**. When a decision is clarified or
  superseded, record the clarification in section 5 of this file and say so explicitly.
- Test printing (Print → Save as PDF) after any change to the report's layout.
