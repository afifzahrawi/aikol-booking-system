# AIKOL Room and Vehicle Booking System

A web-based resource booking system for the **Ahmad Ibrahim Kulliyyah of Laws (AIKOL)**,
**International Islamic University Malaysia (IIUM)**. It covers two kinds of bookable resource:

- **Venues** — moot court, seminar rooms, meeting rooms, lecture rooms, discussion rooms.
- **Vehicles** — Kulliyyah cars, bookable by lecturers and staff.

Students, lecturers, staff and members of the public check availability, submit booking requests and
follow their status; the Kulliyyah office approves, rejects and cancels bookings, assigns drivers,
issues and receives keys, and maintains resources, users and reports.

## Status

**Phase 1 and 2 are complete** — discovery, the management review package, and a nineteen-screen
interactive prototype. AIKOL has answered all twenty-six management decisions and several follow-up
questions. **Phase 3 (Django project, database, authentication) has not started.**

There is no backend yet. The prototype runs entirely in the browser on fictional demonstration data.

## Running the prototype

No build step, no dependencies, no server. Open the landing page in a browser:

```
prototype/index.html
```

It links every screen. The management review report is a separate document:

```
management-report/index.html
```

Both are static files that work from the file system, on a restricted network, or from a USB drive.

## Repository layout

```
CLAUDE.md              Persistent technical memory — architecture, confirmed decisions, status.
                       Read section 5 before writing any code.
docs/technical/        Architecture, database schema, booking rules, retention, security,
                       testing strategy, bulk import, prototype guide.
management-report/     The Phase 1 deliverable for AIKOL management (HTML, printable to PDF).
prototype/             The interactive UI prototype — 19 screens, one stylesheet, one data file.
design/                Design canvases and the confirmed visual direction.
tools/                 Placeholder image generator.
```

## What the system does

Confirmed by AIKOL and implemented in the prototype:

- Self-registration open to **the public as well as IIUM**; IIUM students supply a matriculation number.
- **Every** booking requires approval. Three roles: user, approver, administrator.
- Bookings up to **90 days** ahead, maximum **9 hours** each, within an **08:00–22:00** window.
- Users cancel their own bookings up to **3 days** before, with a mandatory reason.
- **Recurring bookings** — a whole semester entered once, with clashes reported rather than skipped.
- **Vehicles** are requested by lecturers and staff; **an administrator assigns the driver**, never
  the requester. The Kulliyyah provides no driver of its own. Transport for a student activity is
  arranged through the Vehicle Management Unit via STADD, outside this system.
- **Key collection and return** recorded against each booking.
- Booking confirmation email, administrator-managed facilities, editable header and footer content.
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

## Planned stack

Python 3.11+ / Django 5.x LTS · Django templates + Bootstrap 5 (vendored, no CDN) ·
PostgreSQL in production, SQLite in development · Nginx + Gunicorn · Django's own authentication
(no IIUM single sign-on) · cron for scheduled jobs, no message queue.

## Notes on this repository

- **Demonstration data is fictional.** Accounts use `@demo.aikol.test` addresses; venues, vehicles,
  bookings and names are invented for design review and do not represent real AIKOL records.
- **Images are generated placeholders** watermarked as such, pending real photographs from the
  Kulliyyah.
- AIKOL's verbatim answers to the twenty-six decisions are held internally and are not published
  here; the decisions themselves are recorded in section 5 of `CLAUDE.md`.

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
