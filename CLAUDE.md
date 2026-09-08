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

**Phases 1 to 5b are COMPLETE.**
**All 26 section 24 decisions have been answered by AIKOL** (see section 5).
The Django project exists, the database is built, authentication works, resources are browsable
and manageable, and **bookings can be submitted, decided and cancelled** — single and recurring.
Phase 6 (administrative features and key custody) is next.

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

### Not started

Phases 6–10: administrative features, key custody, reporting, bulk data, deployment.

### Next step

Phase 6 — administration and key custody. The `KeyHandover` model already exists with its four
people (who booked, who collected, who issued, who received); Phase 6 is the issue and return
screens, the outstanding-keys report, and booking on a user's behalf.

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
├── docs/
│   ├── README.md
│   └── technical/              # architecture, schema, booking rules, retention,
│                               # security, testing, bulk import, prototype guide
└── tools/
    └── generate_placeholder_images.py
```

The Django project is in `aikol_booking/` at the repository root, laid out as
`docs/technical/architecture.md` specifies: `config/settings/` split three ways, `apps/` holding the
eight modules, plus `templates/`, `static/`, `media/` and `requirements.txt`. The virtual environment
lives in `.venv/` and is not committed. Migrations **are** committed.

The prototype covers venues only. Vehicle screens — a vehicle list, a vehicle detail page, a trip
booking form with driver and licence fields, and a key issue/return screen — do not exist yet.

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
| Email | **SMTP, sent from a database outbox by cron** | Account email *and* booking confirmations. See section 6 |
| Scheduled jobs | **cron calling `manage.py`** | `COMPLETED` transition, retention scans. No Celery |
| Charts (app) | Plain HTML/CSS; **Chart.js** only if a chart genuinely needs it | Vendored if adopted |
| Web server | **Nginx + Gunicorn** | |
| Hosting | **Self-provided VPS, not IIUM ITD** | Confirmed decision |
| Domain | **Self-provided, not an IIUM subdomain** | Confirmed decision |
| Version control | **Git** | |
| Testing | Django test framework | `manage.py test`. 164 tests as at Phase 5 |
| Image handling | **Pillow** | Required by Django's `ImageField`. Not optional — resource photographs are a confirmed requirement |
| PostgreSQL driver | **psycopg 3** | Production only. Installed in development so `check --deploy` can run |
| Cost | **RM 0 in software.** Hosting and domain are now a real recurring cost | See section 5 |

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
| Who may book a vehicle | **Anyone may book, students included.** Eligibility to *book* and eligibility to *drive* are different things — see the next row |
| Trip length | **Multi-day trips are allowed.** A vehicle may be collected one day and returned another; a system setting caps the maximum trip length |
| Driver | Two arrangements. **Self-drive** — lecturers and staff only, with a licence number and expiry on file. **VMU driver** — a driver supplied by the Vehicle Management Unit. **A student may never drive a Kulliyyah car**, so a student's booking must request a VMU driver |
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

Nothing blocks Phase 3. Two operational items need answers before Phase 10 (deployment):

1. Which VPS provider and specification, and who pays.
2. Which domain name, and where external backup storage lives.

**Never present a decision as established AIKOL process unless it appears above** — in code
comments, in the report, or in conversation with the user.

---

## 6. Database

Full detail in `docs/technical/database-schema.md`. Summary:

`users` · `resources` · `venues` · `vehicles` · `resource_images` · `bookings` ·
`booking_series` · `key_handovers` · `booking_archive` · `audit_logs` · `system_settings`

Key decisions:

- **Custom user model** (`accounts.User`) with `email` as the login field, plus
  `identification_number` (matriculation or staff number, unique), `phone`, and the driving licence
  fields. Set this up in the very first migration — it cannot be changed later without pain.
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
  round-trips. This is not a message queue and does not reopen that decision.
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
- Driving licence numbers and telephone numbers are personal data. They appear in exports only where
  the export's purpose requires them, and never in the audit log's free-text description.

---

## 9. Security requirements

Django's built-in authentication with hashed passwords — never a hand-written scheme, never plain
text. The system provides its own authentication; there is no IIUM SSO and none is planned
(decision 24), so account security is entirely this system's responsibility.

**Self-registration** is open but constrained: the email address must end in `@iium.edu.my` or
`@live.iium.edu.my`, the address must be confirmed by a verification link before the account can
book anything, and a matriculation or staff number is required and unique. Rate-limit registration
and password-reset requests — a public registration form on a public domain will be probed.

Role-based authorisation checked in every view (403, not a hidden menu item), across three roles:
standard user, **Approver** (decides bookings only), and Administrator. Vehicle booking is further
restricted to lecturers and staff; enforce it in the form and the view, not only by hiding the link.
Ownership checked on the object, never inferred from the URL. CSRF on every form. Template
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
- The identity is carried by the **pointed-arch frame** (`--arch`, applied to the building
  photograph and room galleries), the Arabic greeting on the dashboard, and a faint girih crosshatch
  over resource imagery. There is deliberately no other ornament — no crescents, no mosque
  silhouettes, no Arabic-styled Latin type.
- The **real AIKOL wordmark** (`assets/images/aikol_logo.png`) is now in use, at 200 px in the brand
  bar. It is no longer a placeholder.

---

## 11. First release (MVP)

**In:** self-registration with IIUM email verification · authentication and password reset ·
three roles (user, approver, administrator) · user management with activation/deactivation ·
venue management with images · **vehicle (car) management with images** ·
**administrator-managed facility list** · **editable header and footer content** ·
**booking confirmation email** · resource browsing,
filtering and details · availability display · booking submission for venues and vehicles ·
**multi-day vehicle bookings** · **self-drive or VMU-driver arrangement with the second, management approval** · **recurring bookings** · conflict prevention with tests ·
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
| 6 | Administrative features, approver role, booking on behalf | Not started — **next** |
| 6b | Key issue and return recording | Not started — added by decision 17 |
| 7 | Bulk data, reporting and retention | Not started |
| 8 | Testing and security review | Not started |
| 9 | User acceptance testing | Not started |
| 10 | Deployment and training | Not started — needs VPS and domain decisions |

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
