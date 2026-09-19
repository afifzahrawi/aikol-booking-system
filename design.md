# Design: AIKOL Court Docket

This is the locked visual and interaction system for the Django application. It replaces the
prototype-derived header/card/table world while preserving every business rule and route.

## World

Contemporary legal chambers and docket books, interpreted as an operational interface rather than
period decoration. Every booking is a case file: it has a stable reference, parties, resource,
schedule, purpose, decisions, custody history and one next action. AIKOL's legal identity is present
in the reading order and record structure; it is not expressed through gavels, scales or courthouse
clip-art.

## Composition

- Desktop uses a narrow collapsible docket rail, an index/list region and a focused record workspace.
- Requester screens use the same record language at lower density, with five destinations at most.
- Administrator screens have one global rail only. Local room/car switches are segmented controls
  inside the Bookings or Resources workspace, never a second global navigation matrix.
- Record pages read in order: identity and state; date and time; parties; purpose; decisions; custody;
  history. The next valid action remains easy to find.
- The signed-in profile forms one compact control at the bottom of the navigation rail. Opening it
  reveals Edit Profile and Sign Out; Sign Out uses subdued oxblood. The collapsed rail retains the
  profile avatar and every destination icon, with labels returning when expanded. A small edge
  control collapses the rail without occupying a navigation row. The rail does not carry a
  redundant "My docket" or role heading.
- The institutional masthead remains anchored at the top and the desktop rail remains fixed beneath
  it while records scroll. The footer uses IIUM teal to distinguish it from the darker docket rail.
- Mobile replaces the rail with a compact header and bottom task navigation. Tables that are not
  genuinely comparative become docket rows; forms become one readable column.

## Materials and colour

- `docket ink` `#172522`: primary text.
- `deep IIUM teal` `#0a4541`: desktop rail.
- `vellum` `#f2eee3`: application background.
- `brief paper` `#fffdf7`: active record surface.
- `AIKOL green` `#14675b`: action, selection and institutional structure.
- `brass` `#b9892f`: AIKOL/IIUM identity, dates and restrained emphasis.
- `oxblood` `#963f3a`: destructive and rejected states only.
- `blue ink` `#315f78`: informational states.
- Rules use warm neutral ink at low contrast; shadows are reserved for the active record sheet.

Status must never rely on colour alone. Every status has a word, a compact stamp shape and, where
useful, its date or next action.

## Type

- Amiri remains for the organisation name and major institutional moments.
- IBM Plex Sans carries navigation, forms and prose.
- References, dates, times and counts use IBM Plex Mono or the system monospace with tabular figures.
- Body text is 15 px; nothing that carries meaning is set below 12 px. Labels, help text and
  status stamps sit at 12.8–13.6 px.
- Page titles are direct; no eyebrow labels. Visible headings and tab labels are written in title
  case in the markup — never produced by `text-transform: capitalize`, which capitalises "And".

## Controls and state

- Primary buttons name the actual action: `Submit request`, `Approve booking`, `Record key return`.
- Forms are one column, grouped into short docket sections. Conditional information appears after the
  choice that causes it.
- Searchable comboboxes query the server and expose a keyboard-operable listbox; thousands of users
  are never rendered into a select.
- Conflicts use cross-hatched timing blocks plus text, donated from the Exposure Ledger direction.
- Stable booking and resource references are always selectable text, donated from the records
  catalog direction.
- Focus uses a two-pixel green ring with a paper offset. Error summaries receive focus after submit
  and link to the affected controls.
- Cards and record surfaces use a restrained 12-pixel radius; fields and buttons use 8 pixels. The
  softer geometry must not turn the interface back into a mosaic of floating SaaS cards.

## Photography

The editable AIKOL building image remains on login and Home, but it is contextual evidence of place,
not the application shell. Resource photography uses rectangular crops. IIUM logo appears first,
AIKOL logo second, without a divider between the marks.

## Motion

One easing family and three durations, as tokens: `--ease-out` (a soft exponential ease-out),
`--dur-fast` 120 ms for feedback, `--dur` 220 ms for menus, `--dur-slow` 340 ms for layout. Motion
starts from the visible state, decelerates, and never plays twice for one event.

- Page changes: the shell stays put; the workspace cross-fades and rises 6 px once (280 ms). The
  record sheet does not add a second entrance on top of that.
- Rail: the width is a registered custom property that transitions, so the rail and the workspace
  column move together in one curve; labels fade rather than pop. No whole-page snapshot.
- Menus fade and scale from the control that opened them. Pressed controls scale to 0.97 at once.
- Report bars grow into place when they are drawn. Reduced motion removes spatial movement.
- No decorative loops or blanket transitions. Nothing animates that the person did not cause.

## Responsive contract

- 320 px is supported without document-level horizontal scrolling.
- Touch targets are at least 44 px.
- At phone widths: one form column, persistent task navigation, no compressed desktop action rows,
  and no essential hover state.
- At tablet widths: the fixed left rail remains available; list and record may stack, and filters
  collapse by priority rather than into an unrelated hamburger hierarchy.
- At desktop widths: rail stays fixed, active workspace may use list/detail composition.

## Refusals

No repeated same-size statistic cards as page structure; no duplicate global navigation; no icon
tiles; no generic SaaS gradient; no decorative legal symbols; no rounded-card mosaic; no desktop
table merely made horizontally scrollable as the mobile solution. Active controls use surface and
text contrast, never a decorative coloured strip at the edge.
