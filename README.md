# AIKOL Room and Vehicle Booking System

A web-based resource booking system for the **Ahmad Ibrahim Kulliyyah of Laws (AIKOL)**,
**International Islamic University Malaysia (IIUM)**. It covers two kinds of bookable resource:

- **Venues** — moot court, seminar rooms, meeting rooms, lecture rooms, discussion rooms.
- **Vehicles** — Kulliyyah cars, requested through the VMU/STADD driver route.

Students, lecturers, staff and members of the public check availability, submit booking requests and
follow their status; the Kulliyyah office approves, rejects and cancels bookings, assigns drivers,
issues and receives keys, and maintains resources, users and reports.

## Status

**Phases 1 to 8 are complete.** The Django application is deployed to Google Cloud Run with Neon
PostgreSQL and private Cloudflare R2 storage. The generated Cloud Run hostname is available for
testing. Public launch still depends on a configured SMTP mailbox, remediation and completion of
the recorded UAT cases, a PostgreSQL concurrency check, a final public hostname, and staff handover.

The static prototype remains as historical design material. The live application is in
`aikol_booking/`; its current status and operational constraints are maintained in `AGENTS.md`.

## Running the application locally

Create and activate a Python virtual environment, install the pinned requirements, then run Django:

```powershell
cd aikol_booking
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

For deployment and operational checks, use the Cloud Run guide in `docs/technical/`.

## Running the historical prototype

The prototype has no build step, dependency, or server. Open:

```
prototype/index.html
```

The management review report is a separate printable HTML file at `management-report/index.html`.

## Repository layout

```
AGENTS.md              Persistent technical memory — architecture, confirmed decisions, status.
                       Read section 5 before writing any code.
docs/technical/        Architecture, database schema, booking rules, retention, security,
                       testing strategy, bulk import, prototype guide.
management-report/     The Phase 1 deliverable for AIKOL management (HTML, printable to PDF).
prototype/             The interactive UI prototype — 19 screens, one stylesheet, one data file.
design/                Design canvases and the confirmed visual direction.
tools/                 Placeholder image generator and action-matrix regression runner.
```

## What the system does

Confirmed by AIKOL and implemented in the Django application:

- Self-registration open to **the public as well as IIUM**; IIUM students supply a matriculation number.
- **Every** booking requires approval. Three roles: user, approver, administrator.
- Bookings up to **90 days** ahead, maximum **9 hours** each, within an **08:00–22:00** window.
- Users cancel their own bookings up to **3 days** before, with a mandatory reason.
- **Recurring bookings** — a whole semester entered once, with clashes reported rather than skipped.
- **Vehicles** may be requested by any eligible user, including students. **An administrator assigns
  the VMU driver**, never the requester, and Kulliyyah management records a second decision before
  a vehicle key can be issued.
- **Key collection and return** recorded against each booking.
- Booking confirmation email, administrator-managed facilities, editable identity and page
  photography, editable login introduction, and scheduled home-page announcements.
- Booking records retained **7 years**, then exported rather than deleted.

## The rule the design rests on

For any resource, a new booking conflicts with an existing one when:

```
new_start < existing_end  AND  new_end > existing_start
```

counting only bookings that are `PENDING` or `APPROVED`. Venues and vehicles share one `resources`
table and one `bookings` table with timestamp columns, so a two-hour seminar slot and a three-day car
trip are checked by exactly the same rule — implemented once, tested once, and enforced in the
browser, on the server, and by a PostgreSQL exclusion constraint.

## Production stack

Python 3.11+ / Django 5.x LTS · Django templates + Bootstrap 5 (vendored, no CDN) ·
PostgreSQL in production, SQLite in development · Google Cloud Run + Gunicorn + WhiteNoise ·
Neon PostgreSQL · private Cloudflare R2 storage · Django's own authentication (no IIUM single
sign-on) · Cloud Scheduler for maintenance, no message queue.

## Notes on this repository

- **Demonstration data is fictional.** Accounts use `@demo.aikol.test` addresses; venues, vehicles,
  bookings and names are invented for design review and do not represent real AIKOL records.
- **Images are generated placeholders** watermarked as such, pending real photographs from the
  Kulliyyah.
- AIKOL's verbatim answers to the twenty-six decisions are held internally and are not published
  here; the decisions themselves are recorded in section 5 of `AGENTS.md`.

## Licence

**Apache License 2.0** — see [LICENSE](LICENSE). You may use, modify and redistribute this software,
including commercially, provided you keep the copyright notice, state what you changed, and include
the [NOTICE](NOTICE) file.

### If you reuse this, remove the university's identity first

The licence covers the **software**. It does not grant any right to the names, logos or institutional
identity of IIUM or of the Ahmad Ibrahim Kulliyyah of Laws — Apache 2.0 section 6 reserves
trademarks explicitly, and NOTICE sets out what that means here.

Before deploying this for another institution, replace the AIKOL wordmark, the institution name,
address, telephone number and email address, and any wording that presents the system as an IIUM
service. The code is arranged so this is a configuration task rather than a code change: the wordmark
is uploaded through the Site Content screen, the header and footer are stored as settings, and the
palette is one block of custom properties at the top of `prototype/css/styles.css`.

Copyright rests with the Kulliyyah, not with individual contributors.
