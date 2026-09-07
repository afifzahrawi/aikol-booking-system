# Security

Proportionate institutional security. The system holds names, email addresses, matriculation and
staff numbers, telephone numbers, driving licence details and a record of who used which room or car
and when. That warrants care, not the controls appropriate to a financial system.

Two confirmed decisions raise the stakes above the original design:

- **There is no IIUM single sign-on** (decision 24). This system is the only thing standing between
  a stranger and an AIKOL account. Authentication is not delegated to anyone.
- **Hosting is self-provided, not IIUM ITD** (decisions 22 and 23). Operating-system patching,
  firewall configuration, TLS renewal and backup verification belong to this project. No
  institutional IT department is doing them in the background.

## Authentication

- Django's built-in authentication. **Never** a hand-written password scheme.
- Passwords hashed with PBKDF2 (Django default) or Argon2. Plain-text storage is prohibited, and
  administrators cannot view a password.
- Password reset by emailed single-use token. Administrators trigger a reset; they never set a
  password on a user's behalf.
- Session cookies: `HttpOnly`, `Secure`, `SameSite=Lax`, with a defined expiry.
- Deactivated accounts (`status = INACTIVE`) cannot sign in, checked on every request.

## Self-registration

Registration is open, because one administrator cannot hand-create accounts for a whole Kulliyyah.
Open does not mean unguarded:

| Control | Rule |
| --- | --- |
| Email domain | Must end `@iium.edu.my` or `@live.iium.edu.my`. Checked server-side against `system_settings.allowed_email_domains`, not by a browser pattern |
| Verification | Account is created with `email_verified = False` and **cannot book anything** until a signed, time-limited link is followed |
| Identity | Matriculation or staff number required and unique. A duplicate is a registration failure, not a silent merge |
| Rate limiting | Registration, verification resend, sign-in and password reset are all rate-limited per IP and per address |
| Enumeration | Registration with an existing address returns the same message as a new one, and sends a "you already have an account" email instead |

The domain restriction proves an IIUM mailbox, not a current enrolment. A graduated student keeps
their address for a time. Deactivation is the administrator's tool for that; do not pretend the
domain check is doing more than it does.

## Authorisation

Three roles, and an affiliation that is **not** a role:

| Field | Values | Governs |
| --- | --- | --- |
| `role` | `USER`, `APPROVER`, `ADMINISTRATOR` | What actions are permitted |
| `affiliation` | `STUDENT`, `LECTURER`, `STAFF` | Who the person is — and vehicle eligibility |

- Every view checks the signed-in user's role. Administrative URLs return 403 for standard users —
  they are not merely hidden from the navigation.
- `APPROVER` may approve, reject and cancel bookings, and nothing else. It must not reach user
  management, resource management, **facility management**, system settings, retention or the
  database reset. This is decision 5's entire purpose: delegation of approval without delegation of
  administration.
- **Vehicle booking is open to everyone; self-drive is not.** Any active user may request a car,
  but `driver_arrangement = SELF` requires `affiliation in (LECTURER, STAFF)` and a licence on
  file. A student posting `SELF` directly must be refused by the **view**, not merely by a hidden
  radio button — this is the one vehicle rule with a real safety and insurance consequence behind
  it, so it is checked server-side on every submission and again at approval.
- Ownership is checked on the object: a user may view or cancel a booking only if
  `booking.user_id == request.user.id`. Never trust an ID in the URL. Note that a booking created on
  someone's behalf has a different `created_by` — ownership follows `user_id`, not `created_by_id`.
- Use `LoginRequiredMixin` / `UserPassesTestMixin` (or equivalent decorators) consistently; do not
  rely on template logic for access control.

## Personal data

Beyond names and email addresses, the system now holds identifiers and licence details. Handle them
accordingly:

- Driving licence numbers, telephone numbers and matriculation numbers **never** appear in
  `audit_logs.description`, which is broadly readable by administrators and is retained
  indefinitely.
- They appear in a CSV export only where that export's stated purpose requires them. The user export
  includes them; the booking utilisation report does not.
- Licence details are visible to the owning user, approvers deciding a vehicle request, and
  administrators. Not to other users.
- Retention exports (decision 20) contain personal data, so the exported files inherit the same
  storage and encryption rules as backups.

## Outbound email

Every booking status change now emails the requester, so mail is part of ordinary operation rather
than of signup alone.

- **Address resolved at queue time** and stored on the outbox row. A later change of address must not
  redirect mail about an old booking to a new mailbox.
- **Sent to `booking.user` only** — the person the booking is for. Not to `created_by`, not to a
  department list. A booking made on someone's behalf tells that person, not the office.
- **No personal identifiers in the body.** A confirmation carries the reference, resource, period,
  purpose and status. It does not carry matriculation numbers, telephone numbers or licence details:
  email is the least controlled channel the system has, and it is frequently forwarded.
- **No unsubscribe link.** These are transactional messages about the recipient's own booking, not
  marketing. Do not build an opt-out that would let a user silence a rejection notice.
- **Templates are rendered server-side with autoescaping.** User-supplied text — purpose,
  rejection reason, cancellation reason — appears in the body and must be escaped in the HTML part
  exactly as it is in a template.
- **Failures are logged, not surfaced to the requester.** A delivery failure is an operational
  problem; the booking itself succeeded and the user has already seen the confirmation page.

## Editable site content

The header and footer wording is administrator-editable (`system_settings`), which makes it
user-supplied text rendered on **every page of the system**, signed-in or not. Two rules follow:

- **Escape on output, always.** These values are rendered through the template's autoescaping like
  any other user text. A field containing `<script>` must appear as those characters, never execute.
  The prototype's `contentLines()` helper escapes before it converts newlines to `<br>` for exactly
  this reason — the order matters.
- **Administrator only.** Approvers and standard users get 403. An approver who could rewrite the
  footer could quietly change the office telephone number the whole Kulliyyah dials.

Treat the footer link addresses as untrusted too: render them as ordinary links, never as a
redirect target the application follows.

## Web attack surface

| Concern | Mitigation |
| --- | --- |
| CSRF | Django CSRF middleware on every form; never exempted |
| XSS | Template auto-escaping. `\|safe` and `mark_safe` require review; user text is never rendered as markup |
| SQL injection | ORM with parameterised queries throughout. No string-formatted SQL |
| Clickjacking | `X-Frame-Options: DENY` |
| Transport | HTTPS enforced, HTTP redirected, HSTS enabled in production |
| Host header | `ALLOWED_HOSTS` set explicitly |
| Open redirect | Redirect targets validated against a known set |
| Enumeration | Sign-in, registration and password reset return the same message whether or not the account exists |
| Automated signup | Rate limiting on the public registration form |

## Input validation

All validation is server-side. Browser validation is a convenience and is assumed to be absent.

- Booking rules (times, durations, trip length, capacity, passenger count, advance limit, licence
  and road tax expiry) validated in the form and the model.
- Recurrence definitions bounded by `maximum_series_occurrences` before expansion — an unbounded
  series is a denial-of-service vector against your own database.
- CSV imports validated row by row before any insert (`bulk-import.md`).
- Numeric and date fields validated for type and range, not only presence.

## File uploads

Resource images (venues and vehicles) and the site wordmark, which an administrator uploads on the
site-content screen.

- Permitted formats: JPEG, PNG, WebP.
- Maximum size 5 MB, enforced server-side.
- Content sniffed (via Pillow) rather than trusting the extension or the declared content type.
- Files renamed on save; the original filename is never used as a path.
- Stored under `MEDIA_ROOT`, outside the code directory, and served by Nginx as static content —
  never executed.
- Images resized and recompressed on upload to bound storage growth.
- **SVG is not accepted**, for the wordmark least of all. An SVG is a document that can carry script,
  and the wordmark renders on every page of the system, signed in or not. PNG, JPEG and WebP only.
- The browser's file picker and the `accept` attribute are conveniences. The declared content type is
  trivially faked, so the size cap and the format check are re-applied on the server, from the file's
  actual bytes, before anything is written.

## Destructive operations

- Restricted by role.
- Preceded by a displayed record count.
- Confirmed by typing an exact phrase.
- Preceded by an automatic backup, copied off-server.
- Written to the audit log.
- The full database reset is disabled by default in production settings.

## Audit log

Append-only. Written for: booking approved, rejected or cancelled by an administrator or approver;
booking created on behalf of another user; key issued and key returned; resource created, modified,
activated or deactivated; user created, modified, activated, deactivated or access reset; bulk
import; data cleanup; database reset. Records actor, action, entity type, entity id, description and
timestamp. Application code never edits or deletes audit rows.

## Server operations

Self-hosted, so these are ours:

- Unattended security upgrades enabled; kernel and Django security releases applied promptly.
- Firewall closed by default; only 80, 443 and an SSH port reachable. SSH by key, root login off.
- TLS via Let's Encrypt with automated renewal, and a monitored expiry date.
- Database not exposed to the network; PostgreSQL bound to localhost.
- Backups copied off-server, encrypted, and **test-restored monthly** (`data-retention.md`).
- Application logs retained and reviewed; failed sign-in bursts are worth noticing.

## Configuration and secrets

- `SECRET_KEY`, database credentials and mail credentials come from environment variables.
  Nothing secret is committed to version control.
- `DEBUG = False` in production, with `ALLOWED_HOSTS` set.
- Error pages never reveal stack traces to users; errors are logged server-side.

## Maintenance

- Apply Django security releases promptly; the Django version in use is recorded in
  `requirements.txt` and in `CLAUDE.md`.
- Review dependencies before adding any; every dependency is a maintenance obligation.
- Run `python manage.py check --deploy` before each production deployment and resolve every warning.
