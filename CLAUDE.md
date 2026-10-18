# CLAUDE.md — AIKOL Room and Vehicle Booking System

Loaded into every Claude Code request, so it holds only what applies to every change. The full
history, all 26 AIKOL decisions, the schema reasoning, the phase log and the architectural "why"
are in **`docs/technical/project-record.md`** — read the section you need, not the whole file.
If this file and the code disagree, that is a defect; fix whichever is wrong in the same change.

## Project and status

Django booking system for **venues and vehicles (cars)** at the Ahmad Ibrahim Kulliyyah of Laws
(AIKOL), IIUM. Requesters check availability and book; the office (Approver, Administrator)
decides, cancels, issues and receives keys, and maintains resources, users and reports.

**Live on Google Cloud Run** (`*.run.app`, no custom domain yet), Supabase PostgreSQL (free plan), Cloudflare R2,
Secret Manager. Phases 1 to 8 complete; **Phase 9, user acceptance testing**, is next. Email is
delivered (Gmail SMTP via the System screen). The staff second factor is **switched off**
(`MFA_ENFORCED = False`, office request, 1 October 2026); setting it to `True` restores it.

Guiding principle: the simplest architecture that reliably meets the requirements. No new
framework, service or dependency without a reason recorded in the project record.

## Where things are

| Need | Look in |
| --- | --- |
| Decisions 1–26, vehicle and registration rules, what is still open | project record §5 |
| Database tables, indexes, setting values | project record §6, `docs/technical/database-schema.md` |
| Booking rules, conflict tests | `docs/technical/booking-rules.md`, `testing-strategy.md` |
| Security design (rate limits, MFA, uploads) | `docs/technical/security.md` |
| Deployment, jobs, backups | `docs/technical/managed-cloud-deployment.md` |
| Visual system | `design.md` (source of truth), `static/css/tokens.css`, `redesign.css` |
| Guides and UAT | `docs/user-guide.md`, `docs/admin-guide.md`, `docs/uat-test-script.md` |

Code: `aikol_booking/` (`config/settings/{base,development,production,build,postgres}.py`,
`apps/` with eight modules, `templates/`, `static/`). Virtualenv `.venv/` at the repository root.
Run tests from `aikol_booking/` with `../.venv/Scripts/python.exe manage.py test <module>`.

## Stack (decided)

Python 3.11+ / Django 5.x · Django templates (no JS framework) · everything vendored, no CDN ·
Amiri + IBM Plex Sans as WOFF2 under `static/` · SQLite in development, PostgreSQL in production
(the overlap exclusion constraint needs it) · Django's own auth, no IIUM SSO · email through the
`email_outbox` table drained by Cloud Scheduler calling the private maintenance service · no
Celery, no queue, no React/Vue, no paid services, no AI feature.

## Rules for every change

**No double bookings.** Same resource conflicts when `new_start < existing_end AND new_end >
existing_start`, counting only `PENDING` and `APPROVED`; adjacent bookings do not conflict.
Checked on submission and again on approval under `select_for_update()`, and by the PostgreSQL
exclusion constraint. One rule and one `bookings` table for venues and vehicles alike. Recurring
bookings are expanded to real rows; clashing occurrences are reported, never silently skipped.

**Data protection.** Cancelling sets a status, never deletes. Users and resources are
deactivated; deletion only through two gates (deactivated first, no booking history — `PROTECT`
enforces it). Audit log is append-only. Retention is 7 years, disposal is export-and-verify.
Backup before any bulk deletion or migration. Phone and matriculation numbers never go in the
audit log's text.

**Security.** Role check in every view (403, not a hidden link); ownership checked on the
object; CSRF everywhere; ORM only; server-side validation; uploads sniffed, 5 MB, images only.

**Settled AIKOL points that are easy to get wrong.** Every booking needs approval. Students may
book venues *and* vehicles; nobody self-drives (anything asking for a licence is a defect). A
vehicle booking has two approvals (office, then Kulliyyah management for the VMU driver). Users
cancel their own bookings outright up to 3 days before, with a reason. Never present something as
AIKOL process unless the project record §5 says so.

**Code.** PEP 8, black, 100-character lines. Fat models and services, thin views. Lists paginate
and filter in the query; watch for N+1. Migrations committed, never edited once applied. Comments
explain why. Email goes through `apps.notifications.wording.send`, never a body composed inline.

**Interface** (full list: project record §10, and `design.md`).
- CSP is `style-src 'self'`: an inline `style=""` does nothing. Use a class or a
  `data-width`/`data-height` attribute.
- `{# #}` is single-line only; use `{% comment %}` for more.
- Bump the `?v=` cache-buster on `redesign.css` in `base.html` and `accounts/login.html` when CSS
  changes.
- Plain copy for a first-time user; no em/en dashes or middle dots in visible text; title case
  headings; no eyebrow labels; on/off settings are Yes/No drop-downs; say "the Admin".
- Every form uses `StyledFormMixin`; image fields use `config.forms.ImageInput`.
- One curve and three durations for motion; `prefers-reduced-motion` turns it off.

## Repository conventions

- Commit messages carry **no Claude co-author trailer**. Do not commit AI-assistant files.
- `Section 24.docx` is AIKOL's own words: never edited, never committed.
- The management report is HTML, never Markdown. Demo data is obviously fictional
  (`@demo.aikol.test`); invented figures are labelled **Illustrative data**.
- When a decision, phase or architectural reason changes, update the project record; touch this
  file only if a rule above changes.

## Working efficiently (token budget)

- Read the one project-record section or doc a task needs; do not open whole large files.
- Run only the affected test modules while working, the full suite once before committing.
- Filter shell output (`tail`, `grep`, counts). Screenshots at scale 0.5 or less, or read page
  text instead.
- Send wide sweeps (multi-page browser checks, design audits, long logs) to a sub-agent on a
  smaller model and bring back findings only.
- Write multi-line Python edits with the Edit/Write tools; shell heredocs here mangle `\n`.
