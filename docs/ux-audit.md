# End-to-end UX audit

Date: 10 September 2026  
Scope: the Django application in `aikol_booking/`, covering requester, approver and administrator
workflows on desktop and mobile.

> **Audit limitation:** this is a single-context review because a separate reviewer process was not
> available in this session. It combines live browser inspection, accessibility-tree inspection,
> responsive measurements, deterministic template scanning, source tracing and the automated test
> inventory. The browser evaluation surface was read-only, so a temporary in-page audit overlay
> could not be injected.

## Executive summary

The system has a stronger functional and security foundation than its current interface suggests.
Conflict prevention, cancellation preservation, staged imports, role checks, upload validation,
retention safeguards and key custody are implemented carefully. The existing visual pass, however,
is still a refinement of the prototype rather than a new design language. It also conceals several
missing operational paths behind otherwise complete-looking screens.

The missing operational paths identified by the audit have now been implemented. Self-drive was
removed by a later requirement decision: every vehicle request uses VMU/STADD. Administrators can
assign the VMU driver and record the separately attributed management decision; the booking register
has Room and Car views; one-off and recurring bookings can be made for a searched account; and
multiple academic calendars with named breaks are maintained in the application.

The selected direction is **Court Docket**: a task-oriented legal-record interface in which resources
have stable identities, requests move through an explicit lifecycle, custody is first-class state,
and the next action is more prominent than explanatory prose. It uses no legal clip art; docket
structure comes from typography, reference numbers, rules, stamps and strict reading order.

## Scorecard

### Nielsen heuristics

| Heuristic | Score | Finding |
| --- | ---: | --- |
| Visibility of system status | 3/4 | Slot feedback, notices and badges work; multi-step requests lack progress. |
| Match with the real world | 3/4 | Booking and key language is concrete; VMU/STADD routing is not represented as a process. |
| User control and freedom | 3/4 | Back and cancellation paths exist; long forms have no draft or safe interruption. |
| Consistency and standards | 2/4 | Two administrator navigation systems and drifting row actions compete. |
| Error prevention | 4/4 | Conflict checks, import preview and destructive gates are strong. |
| Recognition over recall | 3/4 | Labels are explicit; administrator booking creation and secondary actions are buried. |
| Flexibility and efficiency | 2/4 | Search and import help, but booking on behalf uses an unsearchable full user list. |
| Aesthetic and minimalist design | 2/4 | Calm but flat; duplicated navigation and long prose obscure the task. |
| Error recovery | 3/4 | Errors preserve forms and explain conflicts; error-summary focus is inconsistent. |
| Help and documentation | 2/4 | Context exists, but it is verbose and not organised around tasks. |

**Total: 27/40 — acceptable, with material workflow and hierarchy problems.**

### Technical interface health

| Area | Score | Evidence |
| --- | ---: | --- |
| Accessibility | 3/4 | Landmarks, labels, focus and touch sizing are present; long navigation and tables create excessive focus travel. |
| Performance | 3/4 | Small dependency footprint; resource images lack complete lazy-loading and intrinsic dimensions. |
| Responsive behaviour | 3/4 | No page-level overflow at 320/375 px; dense tables remain desktop-shaped and scroll laterally. |
| Theming | 2/4 | A token layer exists, but legacy and redesign CSS overlap and still contain many literal values. |
| Implementation integrity | 3/4 | Templates scan cleanly; inline presentation and duplicated systems create drift. |

**Total: 14/20 — good foundation, but the styling and mobile data patterns need consolidation.**

## End-to-end workflow coverage

Status meanings:

- **Complete** — the route is available, understandable and backed by tests.
- **Friction** — the route works, but its interaction or information architecture needs redesign.
- **Missing** — the intended normal application workflow is absent or cannot be completed.

### Requester and public-user journeys

| Journey or case | Status | UX assessment and required change |
| --- | --- | --- |
| Register as IIUM student, lecturer or staff | Complete | Matric/staff number is required and duplicate checks are safe. Make the affiliation choice the first explicit step instead of explaining it around the fields. |
| Register as a member of the public | Complete | The non-IIUM checkbox works. Replace the negative checkbox label with a direct affiliation choice so users do not have to reason through a negation. |
| Duplicate email or ID | Complete | Account enumeration is resisted. Keep the neutral email response and put actionable field errors at the top and inline. |
| Verify email | Complete | One-use and tampered links are covered. The success screen should state the single next action: sign in. |
| Sign in, sign out and reset password | Complete | Functional and rate-limited. The large photographic login treatment should yield more space to the task on mobile. |
| Read login introduction and announcements | Complete | Content is editable. Announcements need severity, effective period and a compact dismissal/read state rather than identical cards. |
| Search for an available room or car from Home | Complete | Date/time carry into booking and clashes are rechecked. Results should show why each resource fits and provide one primary action. |
| Search with no available result | Friction | The path to Availability exists but is not a guided recovery. Preserve the criteria and offer nearest viable times/resources. |
| Browse and filter rooms | Complete | Query-backed filtering and pagination work. Cards need denser operational metadata and image dimensions/lazy loading. |
| Browse and filter cars | Complete | Road-tax state is correctly hidden from requesters. Explain unavailable cars neutrally without exposing administrator-only details. |
| View resource details, facilities and images | Complete | Facility chips and image management are present. On mobile, put availability and booking actions before the full gallery. |
| Inspect a date's availability | Friction | Accurate but visually sparse. Use a legible time rail with occupied blocks and a sticky date/resource summary. |
| Submit a venue request | Friction | Rules and validation are sound, but the full form reads like an administrative document. Stage it as schedule, purpose, attendance, review. |
| Submit a self-drive vehicle request | Not applicable | Self-drive is not permitted. Unsupported posted values are rejected by the form and service layer. |
| Submit a VMU-driver vehicle request | Complete | Every requester uses VMU/STADD. The record distinguishes ordinary approval from the administrator-recorded management decision and driver assignment. |
| Understand vehicle unavailability | Complete | Expired road tax blocks booking without revealing the date. Keep the neutral requester message and detailed administrator explanation. |
| Create a weekly series with different times per day | Friction | The data model and tests support it. Replace seven permanently visible rows with weekday selection that reveals time controls only for selected days. |
| Apply semester dates and named breaks | Friction | Expansion correctly excludes breaks and reports them. The review step should separate conflicts, breaks and out-of-term exclusions. |
| Accept a partial conflict-free series | Complete | The safe partial path exists and sends one summary email. Make included/excluded occurrence counts scannable before confirmation. |
| View own bookings and history | Complete | Filters and status are present. Group upcoming actions separately from historical records and make series membership visible. |
| View one booking | Complete | Ownership is enforced. Add a lifecycle/timeline that joins request, decisions, cancellation and key custody. |
| Cancel before the 72-hour cutoff | Complete | A reason is mandatory and history is preserved. Show the exact cancellation deadline before the action. |
| Attempt cancellation inside the cutoff | Complete | Correctly refused. Give the user an administrator-contact recovery route instead of ending at a rule statement. |
| Receive booking emails | Complete | Submission, decision and cancellation are queued safely. Surface delivery state to administrators without exposing personal data. |

### Approver journeys

| Journey or case | Status | UX assessment and required change |
| --- | --- | --- |
| Find pending venue and vehicle requests | Friction | The queue works, but a resource filter substitutes for the requested in-page Rooms/Cars selector and operational counts. |
| Assess one request | Friction | The decision page shows details, but not a compact conflict, policy and history summary in a decision-ready order. |
| Approve a request | Complete | Approval rechecks conflicts and records actor/time. Keep the database-backed safety and make the resulting next step explicit. |
| Reject with a reason | Complete | Reason and email are enforced. Offer reusable reason suggestions without weakening free-text specificity. |
| Decide a series | Complete | Occurrences are rechecked and overtaken dates are reported. Present exceptions first instead of a long homogeneous list. |
| Cancel despite the user cutoff | Complete | Authorised roles are correctly exempt. The UI must distinguish administrative cancellation from rejection. |
| Access only approval authority | Complete | The approver/administrator boundary is tested. The navigation should contain only destinations this role can use. |

### Administrator journeys

| Journey or case | Status | UX assessment and required change |
| --- | --- | --- |
| Read operational overview | Friction | Useful metrics exist, but stat cards repeat the prototype and do not lead into actionable queues. |
| Use a consolidated Bookings workspace | Complete | The Court Docket register has separate Rooms and Cars views, counts, filters, next actions and a first-class Create booking entry. |
| Create a one-off booking for another user | Complete | The administrator selects a resource, then searches active verified accounts through a bounded server-backed combobox. |
| Create a recurring booking for another user | Complete | Recurrence records the selected subject separately from the administrator who created it. |
| Assign a VMU driver | Complete | An administrator assigns the VMU driver after ordinary approval. |
| Record management approval for VMU use | Complete | The second decision has its own status, actor, timestamp and reason; rejection releases the vehicle. |
| Issue a room or vehicle key | Complete | The four-person custody record is strong. Reframe the register around Awaiting collection, Out and Overdue queues. |
| Return a key | Complete | Duplicate/invalid returns are prevented and audited. Put collector/returner identity beside the event timeline. |
| Manage rooms | Complete | Create, edit, image, deactivate and gated delete exist. Replace four equal row buttons with one primary action and an overflow menu. |
| Manage cars | Complete | Same image workflow as rooms and administrator-only road-tax information are present. Keep room/car parity in the new shell. |
| Deactivate or delete a resource | Complete | The two deletion gates are correctly enforced. Show the gate state before the administrator enters the delete screen. |
| Manage resource photographs | Complete | Server validation is strong. Add crop/focal-point control for login/home hero use and display image dimensions. |
| Manage facilities | Complete | Create, rename, deactivate, reorder and protected delete work. Add usage counts before deactivation. |
| Manage users | Complete | Role and activation management work. Add direct links from a user to their bookings and eligibility state. |
| Add or update a driving licence | Not applicable | Requesters cannot self-drive; licence data is not collected. |
| Manage multiple academic calendars | Complete | Administrators can create and edit non-overlapping terms with named, non-overlapping breaks. |
| Edit settings | Complete | Rules are editable and audited. Group them by booking, vehicle, cancellation and retention domains with units beside values. |
| Edit logos, login/home images and introduction | Complete | The content editor works. Add preview context, image crop/focal point and clearer distinction between global identity and page content. |
| Create and schedule announcements | Complete | CRUD and date windows work. Add severity, audience and placement so announcements do not all compete equally. |
| Import users/resources with preview | Complete | Two-step validation is strong and reports all row issues. Keep the preview as a dedicated review step with downloadable errors. |
| Export records | Complete | Role restrictions, auditing and personal-data separation are tested. State scope and included columns before download. |
| Review reports | Friction | Reports are accurate, but their styling remains prototype-like and the metrics do not consistently link to the records behind them. |
| Review audit history | Complete | Read-only and privacy-aware. Add event-category filters and a side panel for structured changes. |
| Review and execute retention | Complete | Typed confirmation, verified export and audit records are strong. Maintain the deliberate multi-step treatment. |

## Priorities

### Completed required journeys

1. Removed self-drive and obsolete requester licence data.
2. Added administrator-only VMU driver assignment and a properly attributed second management
   decision workflow.
3. Added the administrator Bookings workspace, searchable booking-for selection, recurring booking
   on behalf, and multiple academic calendars.

### P1 — required workflow or systemic usability failure

1. Turn complex booking forms into short, conditional steps with a persistent review summary.
2. Replace remaining horizontal mobile tables with task-specific cards or list rows; reserve tables for
   genuinely comparative data.

### P2 — quality and clarity

1. Consolidate `app.css` and `redesign.css` into one tokenised design system and remove inline styles.
2. Add image loading metadata and crop/focal-point controls.
3. Connect dashboard statistics and reports to actionable filtered lists.
4. Align status terms and represent every booking as one comprehensible lifecycle.

## Recommended information architecture

The Court Docket shell separates requester navigation from operational administration instead of
appending a second administrator menu to the first.

**Requester:** Find · My bookings · Rooms · Cars · Account  
**Approver:** Queue · Decisions · History  
**Administrator:** Overview · Bookings · Keys · Resources · People · Insights · System

On desktop, administrator work should use a compact left rail with counts and one content toolbar.
On mobile, it should use a small primary navigation plus a task switcher; dense record lists become
stacked rows with the next action exposed and secondary actions in a menu.

## Proposed visual direction

The visual language should move away from the prototype's repeated warm card/table pattern while
retaining AIKOL-first and IIUM-second identity, green and gold as institutional anchors, the editable
photography and restrained Islamic character.

The recommended structural metaphor is a **library circulation desk**:

- every room, car, key and booking has a stable record identity;
- availability and custody are first-class state, not decorative badges;
- the interface is organised around Find, Request, Decide, Issue and Return;
- compact index rows support scanning, while a record drawer or detail page carries history;
- due dates, conflicts and overdue keys use precise time language;
- mobile screens become single-record task surfaces instead of compressed desktop tables.

The expression should be contemporary Malaysian institutional design, not nostalgic library
decoration: light mineral surfaces, deep ink text, AIKOL green for structure, gold for institutional
identity, and one functional alert colour family. Photography is contextual rather than the entire
application shell. Amiri may remain for institutional moments, while a highly legible sans-serif
drives operations.

## Evidence and run notes

- Representative live routes were inspected at 1280, 853, 375 and 320 pixels.
- No document-level horizontal overflow or browser-console errors were observed.
- The deterministic template detector returned zero markup findings, but could not resolve Django
  `{% static %}` stylesheet expressions; its CSS result is therefore incomplete.
- A source count found 73 inline `style` attributes and 134 literal colour expressions across the
  two application style layers.
- The complete Django suite passed immediately before the audit: 297 tests, one skipped.
- The read-only browser evaluation surface rejected the required mutation probe, so no temporary
  `[Human]` overlay was injected. Screenshots, accessibility trees and computed layout evidence were
  used instead.
