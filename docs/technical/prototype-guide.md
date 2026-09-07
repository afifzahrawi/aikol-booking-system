# Phase 1 prototype and report — how they are built

Both deliverables are static files that open directly from the file system. No build step, no
external images, and — apart from the two webfonts the confirmed design requires — no external
assets. They work on a restricted network, from a USB drive, or as an email attachment; without the
fonts they fall back to Georgia and Segoe UI and the layout holds.

Both have been brought into line with AIKOL's answers to section 24 and with the follow-up decisions
on vehicles, self-registration, confirmation email and administrator-managed facilities. Section 5
of `CLAUDE.md` remains the authority for every value.

## Management report — `management-report/`

| File | Contains |
| --- | --- |
| `index.html` | The document: 25 numbered sections, cover, embedded UI mockups |
| `css/report.css` | Institutional styling, mockup components, and the print stylesheet |
| `js/report.js` | Chart rendering, section numbering, table of contents, scroll spy, print button |
| `assets/images/` | Copies of placeholder resource images, so the report is self-contained |

### Section numbering and contents

`report.js` numbers every `<section class="section" id="…">` in document order and builds the table
of contents from their `<h2>` text. **Adding or reordering a section renumbers everything**, so
check in-text cross-references ("see section 18") after any structural change.

Section 24 is still section 24 after the update, so every existing cross-reference to it still
holds.

### Section 24 now carries AIKOL's answers

The decision column was a ruled blank line for management to complete. It now holds the answers,
styled by `.decisions td.answered`, plus a second table recording the decisions taken after the
review (vehicles, registration, email, facilities) and a callout naming the two operational items
still open.

`Section 24.docx` in the repository root holds AIKOL's responses verbatim and is **never edited**.
Where a response needed clarification, the clarification is noted in the report row and in
`CLAUDE.md`, not written back into the source document.

### Charts

Charts are plain HTML and CSS — flex columns with percentage heights — rendered by `report.js` from
data literals at the top of that file. No charting library is loaded. Chart.js was considered and
rejected for Phase 1: the required charts are simple bars, and a dependency that must be vendored,
updated and kept working offline is not worth it. The decision is recorded in section 14 of the
report and is reversible.

**Every figure in the report is illustrative.** Any new chart must carry the
`<span class="tag tag-illustrative">Illustrative data</span>` tag and a caption saying so. Never
present an invented number as an AIKOL measurement.

### Printing

`@page { size: A4 }` with print rules that hide the toolbar and contents, flatten the layout, keep
charts and tables off page boundaries, and preserve colour where it carries meaning (status badges,
diagram nodes). Sections marked `class="section pb"` start a fresh page; the rest flow, which keeps
the PDF compact. Test with **Print → Save as PDF** in Chrome or Edge after any layout change.

The decision column in section 24 is wider now that it carries prose rather than a ruled line, so
re-check that table's page breaks after any change to it.

## Prototype — `prototype/`

Twenty-one screens, implementing the confirmed AIKOL design.

### The design system

`css/styles.css` holds the tokens, lifted from the design file rather than approximated:

| Token | Value | Used for |
| --- | --- | --- |
| `--brand` | `#14675b` | Navigation bar, primary buttons, headings |
| `--gold` | `#d99b28` | Active navigation underline, accents, pending state |
| `--page` / `--surface` | `#f7f4ed` / `#fffdf8` | Warm paper ground and panels |
| `--line` / `--line-soft` | `#ded4bd` / `#ebe3d1` | Panel borders and table rules |
| `--font-serif` | Amiri, Georgia | Headings, resource names, statistic figures |
| `--font-sans` | IBM Plex Sans, Segoe UI | Everything else |
| `--arch` | `24% 24% 6px 6px / 13% 13% 6px 6px` | **The signature pointed-arch frame** |

Three things carry the Islamic and institutional identity, and nothing else does: the **arch** on
the building photograph and room galleries, the **Arabic greeting** on the dashboard, and a faint
**girih crosshatch** over resource thumbnails. Adding crescents, mosque silhouettes or
Arabic-styled Latin type would undo this — the design deliberately avoids all three.

**Two refinements on top of the design file.** Both were asked for after review and both deviate
from `AIKOL Booking 1a.dc.html`, so they are recorded here rather than left to be rediscovered:

- **Statistic figures are set in IBM Plex Sans, not Amiri.** Amiri's Latin uses old-style numerals —
  they vary in height and drop below the baseline, which reads as book typography and stops a column
  of figures aligning. `.stat .v` uses the sans at 600 with `tabular-nums lining-nums`, which is what
  makes a number read as a measurement. No new font is loaded.
- **Table rows carry a coloured leading edge in their own status colour**, plus zebra striping and a
  clearly visible hover. The edge comes from `tintRows()`, which reads the status off the badge the
  row already renders — so no screen passes anything extra and the colour cannot disagree with the
  badge beside it. Where a row has several badges (a role and a status, an expiry date and a status)
  it takes the **last**, because the status column sits at the right. A row may also state
  `data-status` itself, which wins: the approvals queue does this, since its rows carry Approve and
  Reject buttons instead of a badge.

**The sign-in photograph is swappable, and its scrim is load-bearing.** `--login-photo` in
`styles.css` points at the image; the hero layers a gradient over it, over solid green as a fallback.
The gradient never drops below `.74` opacity because that is the point at which white text still
clears 4.5:1 against a pure-white photograph — the worst case. Anyone changing the picture does not
need to re-check contrast; anyone weakening the scrim does.

**Mobile is a real pass, not a reflow.** Breakpoints at 1180, 1024, 940, 640 and 420. Touch targets
hit 44px on phones, and inputs go to 16px there — below that iOS zooms the page on focus, which is
the single most common mobile-form defect. Wide tables and the availability board scroll inside their
own containers so the page never scrolls sideways; the board holds a 660px minimum rather than
crushing seven days into a phone width.

**Navigation is horizontal.** The old left sidebar is gone. `buildChrome()` renders a white brand
bar over a green navigation bar with five items per role: users get Dashboard, Availability, Rooms,
Vehicles, My bookings; administrators get Approvals, Bookings, Resources, Users, Reports. Screens
outside those ten (the key register, vehicle and facility management, data management, the admin
overview) are reached from within them and from `index.html`.

**Fonts come from Google Fonts**, injected by `loadFonts()` so all screens pick them up from one
place. This is the one CDN dependency in the prototype and it contradicts the no-CDN rule in
`CLAUDE.md`: **production must vendor Amiri and IBM Plex Sans as WOFF2 under `static/`.** The
fallbacks (Georgia, Segoe UI) are close enough in metrics that the layout holds without them.

### Screens

| File | Contains |
| --- | --- |
| `index.html` | Landing page listing every screen |
| `login.html`, `register.html` | Sign in, and self-registration with the IIUM domain rule |
| `dashboard.html` | The landing screen — greeting, arch-framed building photograph, one search bar, your activity, browse by type |
| `availability.html` | **The availability board** — rooms by the hour, cars by the day, free time clickable straight into a request |
| `my-bookings.html` | Booking history, status and cancellation |
| `venues.html`, `venue-details.html`, `booking.html` | Room browsing, detail and booking with recurrence |
| `vehicles.html`, `vehicle-details.html`, `vehicle-booking.html` | Vehicle browsing, detail and trip request |
| `admin-approvals.html` | **The decision queue** — approve or reject, with the conflict re-check at approval time |
| `admin-bookings.html`, `admin-keys.html` | All bookings; key issue and return register |
| `admin-venues.html`, `admin-vehicles.html`, `admin-facilities.html` | Resource and facility management |
| `admin-users.html`, `admin-dashboard.html` | Users; administrator overview |
| `admin-reports.html` | **Reports** — utilisation, approval rate, monthly volume, audit log |
| `admin-site-content.html` | **Editable header and footer** — live preview beside the form |
| `data-management.html` | Bulk import, export, retention and backup |
| `css/styles.css` | The design system — tokens lifted from the AIKOL design file |
| `js/prototype.js` | Sample data, the chrome, and all shared behaviour |
| `assets/images/` | 48 generated placeholder images — 32 venue, 16 vehicle — plus the AIKOL wordmark |

`assets/images/AIKOL-building-scaled.jpg` is referenced by the dashboard hero and is **not yet in
the repository**. Until it is dropped in, the arch renders as a plain green panel with a note; the
page does not break.

### `prototype.js`

Exposes one global, `AIKOL`. Its data model mirrors the production schema rather than approximating
it, because the prototype's job is to demonstrate the intended design:

- **`SETTINGS`** — the confirmed business rules (90-day advance limit, 9-hour maximum, 08:00–22:00
  window, 72-hour cancellation cutoff, 7-year retention). Screens read these rather than hard-coding
  numbers, exactly as the production code will read `system_settings`.
- **`resources`** — one collection of 12, made up of `venues` (8) and `vehicles` (4). A booking
  points at a resource, not at a venue, so venues and vehicles share one conflict rule.
- **`facilities`** — a table of 14, not a hard-coded map. Nine are marked `seeded: true` to match the
  data migration; the rest demonstrate facilities an administrator has since created.
- **`bookings`** (~210) — carrying **`startAt` / `endAt` timestamps**. `date`, `start`, `end` and
  `multiDay` are derived from them for display. Thirteen bookings span more than one day, which the
  earlier date-plus-two-times shape could not represent at all.
- **`keyHandovers`**, **`emailOutbox`**, **`series`** — key custody, queued confirmation email, and
  a recurring series whose occurrences are real booking rows carrying `seriesId`.
- **`users`** (46) — with `idNo`, `phone`, and **`affiliation` and `role` as separate fields**, so a
  lecturer can also be an approver.
- **`findConflicts(resourceId, startAt, endAt, ignoreId)`** — the production rule, on timestamps:
  `new_start < existing_end && new_end > existing_start`, counting only `Pending` and `Approved`.
  All fifteen cases from `testing-strategy.md` pass against it, same-day and multi-day alike.
- **`buildChrome`**, **`tableController`**, **`modal`**, **`toast`**, **`emailNotice`** — shared
  behaviour. `tableController` filters and paginates the way the server will, rather than rendering
  everything and hiding rows with CSS.

A small group of deprecated aliases (`venueImg`, `FACILITIES`, `ALL_FAC`, `venueUtilisation`) is kept
at the bottom of the file for anything not yet migrated. New screens must not use them.

### Conventions

- Every screen carries the demonstration ribbon. Sample data must remain obviously fictional.
- **Demonstration accounts use `@demo.aikol.test` addresses**, per the repository convention that
  sample data be obviously fictional. The live system requires `@iium.edu.my` or
  `@live.iium.edu.my`, and `register.html` enforces that rule against typed input — so the rule is
  demonstrated without inventing addresses that could be mistaken for real people's.
- Destructive controls are never one click away: they require a dialogue, and the database reset
  requires a typed phrase.
- Actions that would write to a database explain what the production system would do instead;
  **the prototype never claims to have saved anything**, and never claims to have sent an email.
- Semantic HTML, form labels, `aria-current` for navigation state, alt text on every image,
  keyboard-operable controls. Keep it that way.

### What the screens demonstrate that is easy to miss

| Screen | Behaviour worth reviewing |
| --- | --- |
| `booking.html` | Weekly recurrence expands into concrete dates, and **clashing dates are named rather than silently skipped** — the user chooses whether to submit the remainder |
| `booking.html` | The 9-hour cap is on a single booking, not the day; the form says so when it refuses |
| `vehicle-booking.html` | Licence, road tax and insurance expiry are all checked against the **end** of the trip, not the day it is requested |
| `vehicle-booking.html` | Signed in as a student, the page shows the eligibility block before continuing as staff, so the rule is visible rather than hidden |
| `vehicles.html` | A student sees the fleet and the reason they cannot request it, not a missing menu item |
| `admin-keys.html` | Outstanding keys sort first; a booking can be `Completed` with its key still out |
| `admin-facilities.html` | A facility in use can be deactivated but not deleted; renaming never changes the code |
| `my-bookings.html` | Cancellation refuses an empty reason, and "Why not?" explains the 3-day cutoff instead of just disabling the control |

## Placeholder images

Generated by `tools/generate_placeholder_images.py` — 4 views each for 8 venues and 4 vehicles,
48 SVG files. Each is watermarked `PLACEHOLDER IMAGE` so it cannot be mistaken for a photograph of a
real AIKOL facility or vehicle.

```bash
python tools/generate_placeholder_images.py
```

Slugs avoid trailing digits (`seminar-a`, `car-saga`) because variants are suffixed `-v2`, `-v3`,
`-v4`; a slug ending in a digit would collide with a variant filename.

Vehicle views are: side profile, registration plate with road-tax and insurance panels, features,
and seating layout. The car diagram is anchored to the ground line so the wheels sit on it whatever
roof height the body uses — see `car_body()`.

Replace all of these with real photographs supplied by the Kulliyyah before any production
deployment, and copy the ones used in the report into `management-report/assets/images/` so the
report stays self-contained.

## Branding

The green and gold palette and the `AIK` wordmark are **placeholders**. They are not official
AIKOL or IIUM brand assets. Replace them once brand guidelines are provided; the palette is defined
once as CSS custom properties at the top of each stylesheet.

## Verifying a change

The prototype has no test suite, but three checks catch almost everything and are worth running
after any edit:

1. **Syntax** — extract each page's inline `<script>` and run `node --check` over it.
2. **Element references** — every `getElementById('x')` should have a matching `id="x"` on the page.
3. **Render** — load each page in jsdom with `runScripts: 'dangerously'` and a file-reading
   `ResourceLoader`, and assert no `jsdomError` fires. This catches the broken-reference class of
   bug that syntax checking cannot.

All nineteen screens and the report pass all three.
