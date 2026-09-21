# User Acceptance Test Script

AIKOL Venue and Vehicle Booking System. This script is for the Kulliyyah office and the people
helping them test. It covers every use the system is meant for, large and small. Work through it
in order; the later sections depend on records the earlier ones create.

Print it or copy it into a spreadsheet. For every step write **Pass**, **Fail** or **Skip** and,
for a Fail, what you saw instead. Screenshots help. Anything that made you stop and think, even
if it worked, is worth a note in the last column.

Address: `https://aikol-booking-qn23bk3fqa-as.a.run.app`

---

## Before you start

**People.** Three testers, each with a different role, on their own devices:

| Tester | Role | Uses |
| --- | --- | --- |
| T1, requester | Ordinary user | A real IIUM address you can read mail for, and a phone. Registers fresh in section 1. |
| T2, approver | Approver | An account the administrator sets to Approver in section 12. Needs an authenticator app on their phone (Google Authenticator, Microsoft Authenticator or Authy). |
| T3, administrator | Administrator | The office account. Authenticator app already enrolled. |

**Test data.** T3 creates these in section 11 before T1 starts booking, or use the demo records
if they are still present:

- A venue called **UAT Room** with capacity 10 and one photograph.
- A vehicle called **UAT Car** with 5 seats.
- An academic calendar covering the next two months with one week-long break in the middle.

Name every test record with **UAT** so it can be cancelled or deactivated afterwards. Bookings
are never deleted; cancelled UAT bookings stay in the history, and that is expected.

**Email.** Delivery runs every minute. If a message has not arrived in three minutes, check the
spam folder, then note it as a Fail with the time.

**Devices.** Do each section once on a laptop. Sections 3, 4, 6 and 8 should also be done once on
a phone; mark the phone runs with a P.

---

## 1. Registration and first sign-in (T1)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 1.1 | Open the address. | Sign-in page with the AIKOL and IIUM marks, an introduction and a Sign In panel. Nothing is cut off. | |
| 1.2 | Choose **Register as an IIUM member or public user**. | Registration form. Every field has a label. | |
| 1.3 | Submit the empty form. | The form comes back with a message under each required field. Nothing is created. | |
| 1.4 | Enter a Gmail address as an IIUM member. | Refused: the address must end in `@iium.edu.my` or `@live.iium.edu.my`. | |
| 1.5 | Enter your real IIUM address, name, matriculation or staff number, phone, password. Submit. | "Check your email" page. | |
| 1.6 | Check the inbox. | A message "Confirm your address" within three minutes, from the office's Gmail address. | |
| 1.7 | Try to sign in before clicking the link. | Signed in, but told the address is not yet verified and booking is not possible. | |
| 1.8 | Click the link in the email. | "Address confirmed." You can now book. | |
| 1.9 | Click the same link again. | A polite message that the link has already been used. No error page. | |
| 1.10 | Register a second time with the **same** address. | The page looks exactly like a new registration. No second account appears under People. The inbox receives a "you already have an account" message. | |
| 1.11 | Register a third person with T1's matriculation number. | Refused: that number is already registered. | |
| 1.12 | Sign out. Sign in with the wrong password five times, then the right one. | Each wrong attempt says the email or password is wrong, not which. After ten wrong attempts in a quarter-hour you are asked to wait. | |
| 1.13 | **Forgotten your password?** with your address. | Same "if an account exists" page whether or not the address exists. The reset email arrives within three minutes; the link opens a page to set a new password; the old password stops working. | |
| 1.14 | Use the reset link a second time. | Refused as already used. | |

## 2. Profile (T1)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 2.1 | Profile menu (your name, top right) → **Edit Profile**. | Name, email, phone editable. Matriculation number, affiliation and role shown but not editable. | |
| 2.2 | Change the phone number and save. | Saved; the new number shows. | |
| 2.3 | Change the email address to another address you own and save. | Told the new address must be confirmed; a confirmation email goes to the **new** address; until you click it, booking is paused. | |
| 2.4 | Confirm the new address, then change it back. | Both confirmations work. | |
| 2.5 | Clear the phone number and save. | Refused: a phone number is required (the office needs it for key collection). | |

## 3. Finding a venue or vehicle (T1)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 3.1 | Home page. | Greeting with your name, the quick availability search, announcements, your booking summary. Title left-aligned. | |
| 3.2 | **Venue** in the menu. | Cards with photograph or drawing, name, type, location, seats. UAT Room is present. | |
| 3.3 | Search for "UAT". | Only UAT Room remains. The address bar shows the search, so the page can be bookmarked. | |
| 3.4 | Filter by minimum capacity 50. | UAT Room (capacity 10) disappears. Clear the filter; it returns. | |
| 3.5 | Filter by a facility, then by availability. | Lists change accordingly. | |
| 3.6 | Open UAT Room. | Detail page: photograph, type, location, capacity, opening 08:00 to 22:00, facilities. No internal code is shown to you. **Book this** and **Check availability** are visible without scrolling on a laptop. | |
| 3.7 | **Check availability.** | Week chart, one row per day, 08:00 to 22:00 axis. Legend: approved, pending, free. | |
| 3.8 | Change the date; use Previous week and Next week. | The chart follows. The weekday is spelled out beside the date. | |
| 3.9 | Enter From 10:00 and To 12:00 in the chart's toolbar. | The chart reloads. Each day label is now a link. | |
| 3.10 | **Vehicles** in the menu; repeat 3.2 to 3.7 for UAT Car. | Same behaviour. Seats shown instead of capacity. | |
| 3.11P | On the phone: Venue list, detail, availability. | No sideways scrolling; the bottom tab bar has Home, My Bookings, Venue, Vehicles, Menu; the chart's hour labels do not overlap. | |

## 4. Booking a venue (T1)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 4.1 | From the availability chart with 10:00 to 12:00 entered, click a weekday two weeks ahead. | The booking form opens with that date, 10:00 and 12:00 already filled. | |
| 4.2 | Submit without a purpose. | Refused with a message at the top naming the field, and under the field. | |
| 4.3 | Purpose "UAT test 1", attendees 5. Submit. | "Request submitted" with a reference like BK-2026MM-NNNN. Email "Booking request received" within three minutes. | |
| 4.4 | Book the **same** room, same date, 11:00 to 13:00. | Refused: already reserved, naming the clash. A pending request holds its time. | |
| 4.5 | Same room, same date, **12:00 to 14:00**. | Accepted. Back-to-back bookings do not clash. Note the reference; it is used in section 7. | |
| 4.6 | 07:00 to 09:00. | Refused: outside 08:00 to 22:00. | |
| 4.7 | 08:00 to 18:00 (ten hours). | Refused: longer than nine hours. | |
| 4.8 | A date four months ahead. | Refused: further ahead than 90 days. | |
| 4.9 | A Saturday or a public holiday, inside 90 days. | Accepted. Weekends and holidays are allowed. | |
| 4.10 | End time before start time. | Refused. | |
| 4.11 | Attendees 50 for a room of capacity 10. | Refused: the room seats 10. | |
| 4.12 | Open the form, then choose **Cancel** or press Escape. | The dialog closes; nothing is created. | |
| 4.13P | On the phone, book UAT Room for a date next week. | Form usable one-handed; date and time pickers are the phone's own; submit reaches the confirmation. | |

## 5. Booking a vehicle (T1)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 5.1 | UAT Car → **Book this**. | Form asks for dates and times, purpose, passengers, from and to locations, and the driver arrangement. It says clearly that a VMU driver is arranged by the office and that Kulliyyah management approval is also needed. | |
| 5.2 | Book a one-day trip two weeks ahead, 08:00 to 17:00, 3 passengers, Gombak to Putrajaya. | Accepted. Email received. | |
| 5.3 | Book a trip that starts one day and returns the next. | Accepted. Multi-day trips are allowed. | |
| 5.4 | Book a trip of ten days. | Refused: longer than the maximum trip length (default 7 days). | |
| 5.5 | Book a second trip overlapping 5.2 by one hour. | Refused: already reserved. | |
| 5.6 | Passengers 9 for a five-seat car. | Refused. | |
| 5.7 | Anything asking for a driving licence anywhere on the form. | There is none. Requesters do not drive. If a licence field appears, Fail. | |

## 6. Weekly bookings (T1, venue only)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 6.1 | UAT Room → **Repeat weekly** (on the detail page). | Form with calendar, first date, repeat until, purpose, and a day-of-week grid where each day has its own times. | |
| 6.2 | Choose the UAT calendar, Tuesday 09:00 to 11:00, from next week until the calendar's end. Continue. | A preview listing every Tuesday that would be created, and separately the Tuesday inside the break as "outside teaching". Nothing is booked yet. | |
| 6.3 | Confirm. | The series is created. One email listing all the dates. Each date appears in My Bookings as its own booking. | |
| 6.4 | Request the same series again. | The preview shows every date as already reserved. You can submit nothing, or leave out the clashes if any date is free. | |
| 6.5 | T3 approves one occurrence, then T1 books a **new** weekly series that clashes with only that one. | Preview separates "already reserved" (the approved one) from the dates that are free; the tick box offers to create only the free dates. | |
| 6.6 | Choose two weekdays with different times in one request. | Both patterns appear in the preview with the right times. | |
| 6.7 | Cancel the whole series from any of its bookings. | Future occurrences are cancelled together with one reason; past ones are untouched. One email. | |

## 7. My Bookings and cancelling (T1)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 7.1 | **My Bookings**. | Figures strip (all, pending, approved) and the list, newest first. References are links. | |
| 7.2 | Filter by status Pending; by time (upcoming, past). | The list follows. "No booking matches the current filters" when nothing does. | |
| 7.3 | Open a booking. | Reference as the heading, room, status, when (one date when it starts and ends the same day), purpose, who it is for. | |
| 7.4 | Cancel the booking from 4.5 (two weeks ahead). | Asked for a reason; the reason is required. Status becomes Cancelled. Email "Booking cancelled". The slot is free again on the chart. | |
| 7.5 | Ask T3 to create a booking for T1 **two days** ahead, then try to cancel it as T1. | Refused: inside the three-day notice. The page says to contact the office. | |
| 7.6 | Try to open another person's booking by changing the number in the address bar. | Refused (403), not shown. | |
| 7.7P | My Bookings on the phone. | Each booking is a stacked record with labels; the full time range is visible. | |

## 8. Second factor for staff (T2, T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 8.1 | T2 signs in for the first time after being made Approver. | Forced to the authenticator setup: a QR code, a manual key, a field for the first code. Nothing else in the system is reachable until this is done. | |
| 8.2 | Scan with the app; enter the code. | Ten recovery codes shown once. Save them. Continue. | |
| 8.3 | Go back to the setup page. | Not available again; the QR code is not shown twice. | |
| 8.4 | Sign out, sign in again. | Password, then a six-digit code, then the dashboard. | |
| 8.5 | Enter a wrong code; enter a code from 8.4 again. | Both refused. After ten wrong codes in a quarter-hour, asked to wait. | |
| 8.6 | Sign in with a recovery code. | Accepted; that code will not work a second time. | |
| 8.7 | T1 (ordinary user) signs in. | No code is asked for. | |
| 8.8 | T3: People → T2 → **Reset authenticator**. | T2's next sign-in is forced through setup again. T3 cannot reset their own. | |
| 8.9 | T3 opens `/admin/login/`. | Sent to the ordinary sign-in page. | |

## 9. Deciding requests (T2)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 9.1 | Sign in as T2. | Administrator View in the profile menu; the rail shows Bookings with a count. | |
| 9.2 | Bookings → **Awaiting Decision**. | T1's pending requests, soonest first, with a Decide button on each. | |
| 9.3 | Open Decide on 4.3. | Dialog with the request's details, any overlapping requests, and a reason field. | |
| 9.4 | Approve without a reason. | Allowed (a reason is optional for approval). Status Approved. Email "Booking approved" to T1. The request leaves the queue. | |
| 9.5 | Reject 4.9 without a reason. | Refused: a reason is required to reject. Add one and reject. Email "Booking not approved" with the reason. | |
| 9.6 | T1 makes two requests for the same free slot in quick succession (two browser tabs, submit both). | Only one is accepted. | |
| 9.7 | Ask T3 to create a booking that overlaps a pending one, then approve the pending one. | Approval is refused because the time is now taken. Nothing double-books. | |
| 9.8 | Open Decide on a request whose start time has already passed. | A warning says so before you decide. | |
| 9.9 | T2 tries People, Settings, Site Content, Resources management. | Refused (403). Approvers decide bookings only. | |
| 9.10P | Approvals on the phone. | Stacked records; Decide button full width; the dialog fits. | |

## 10. Vehicle management decision and keys (T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 10.1 | T2 approves the vehicle request from 5.2. | Status Approved, but the booking shows management decision **Pending**. | |
| 10.2 | T3 → Keys → try to issue the key for that vehicle booking. | Refused: it still needs Kulliyyah management approval. | |
| 10.3 | T3 opens the booking → **Management decision**. Enter driver name and contact, approve. | Management status Approved; driver recorded. Email "Vehicle use approved" to T1. | |
| 10.4 | For another vehicle booking, reject at the management step with a reason. | The booking becomes Rejected. Email "Vehicle use not approved". | |
| 10.5 | Keys → **Awaiting Collection**. | Approved bookings whose keys are not yet out, including 4.3 and 10.3. | |
| 10.6 | Issue the key for 4.3: collector's name. | Moves to **Keys Out** with time out, who collected, who issued. | |
| 10.7 | Issue the same key again. | Refused: already out. | |
| 10.8 | Return the key with a note. | Moves out of Keys Out; time in and who received recorded on the booking. | |
| 10.9 | Let a booking with a key out pass its end time (or use one from the demo data). | Appears under **Overdue**; the Overview shows "1 key still out after the booking ended". | |
| 10.10 | T1 tries Keys. | Refused (403). | |

## 11. Venues, vehicles, facilities and images (T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 11.1 | Resources → Venues → **Add venue**. Create UAT Room 2 with no photograph. | Created; shows a drawing as placeholder. | |
| 11.2 | Edit it: change capacity and location. | Saved; the list updates. | |
| 11.3 | Images: upload a JPEG under 5 MB. | Appears; the first image becomes the main image. Upload a second and reorder. | |
| 11.4 | Upload an SVG file; then a 6 MB photograph; then a `.exe` renamed to `.jpg`. | Each refused with a plain reason. | |
| 11.5 | Set UAT Car to **Maintenance**. | Disappears from the Vehicles list for T1; T1 cannot open its booking form; existing bookings are untouched. Set it back to Available. | |
| 11.6 | Try to **Delete** UAT Room 2 while it is active. | Refused: deactivate first. Deactivate, then delete: it is gone. | |
| 11.7 | Try to delete UAT Room (which has bookings). | Refused: it has bookings. It can only be deactivated. | |
| 11.8 | Facilities: add "UAT Projector", rename it, drag it to the top, deactivate it. | Each step saves; the order persists after reload; a deactivated facility disappears from the venue form and the filter. | |
| 11.9 | Academic Calendars: create the UAT calendar with a break; try a second calendar overlapping it. | The overlap is refused. | |
| 11.10 | Numbers in every table (capacity, seats, bookings). | Left-aligned under their headings. | |

## 12. People (T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 12.1 | People. Search T1 by name, by email, by number. Filter by role and state. | Found each way. | |
| 12.2 | Edit T2: role Approver. Save. | Saved. T2 is now forced through authenticator setup at next sign-in (section 8). | |
| 12.3 | The edit form. | No password field anywhere. Labels read "Active account" and "Email address verified", not field names. | |
| 12.4 | Untick **Active account** for a throwaway user; that user tries to sign in. | Refused as if the password were wrong. Their bookings remain in the history. | |
| 12.5 | Tick **Email address verified** by hand for a user whose email failed. | They can book. The change appears in the Audit Log. | |
| 12.6 | Edit dialog: the buttons and the Authenticator section. | Clear space between the Save row and the Authenticator heading. | |

## 13. Settings and email (T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 13.1 | System → Booking Rules. | Each rule has a plain name and a one-sentence description with the default explained. No decision numbers. | |
| 13.2 | Change **Cancellation notice** to 48 and save; ask T1 to cancel a booking 60 hours ahead. | Now allowed. Set it back to 72. | |
| 13.3 | **Reason to cancel** is a Yes/No choice. Set No; T1 cancels without a reason; set Yes again. | Works both ways. | |
| 13.4 | Enter "ninety" in **Book ahead limit**. | Refused. | |
| 13.5 | Email delivery: untick Enable and save. T1 requests a password reset. | Nothing arrives; the yellow notice counts one queued message. Re-enable; it arrives within a minute or two. | |
| 13.6 | Every change above. | Appears in System → Audit Log with who, when and old and new values. | |

## 14. Site content and announcements (T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 14.1 | Change the header subtitle and office hours; reload as T1. | Header and footer change. | |
| 14.2 | Upload a new login photograph and a new home photograph. | Login page and home page change; the marks stay. | |
| 14.3 | Add an announcement "UAT notice" starting now with no end. | Appears on T1's home page. | |
| 14.4 | Add one scheduled to start tomorrow. | Not shown today. | |
| 14.5 | Deactivate the UAT notice. | Disappears; still listed under Site Content as inactive. | |

## 15. Reports and data (T3)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 15.1 | Insights (Reports): 30, 90 days, a year. | Figures strip, demand by hour and day, bookings per month, utilisation, keys, frequent requesters. No "Illustrative" label. | |
| 15.2 | **Export bookings**. | A CSV opens in Excel with the UAT bookings, no passwords, and the columns the office expects. Note any column missing. | |
| 15.3 | System → Data: download the venue template; add two rows, one deliberately wrong (missing name). Upload. | Preview lists the wrong row with its line number and reason; nothing is written. | |
| 15.4 | Fix the row and upload again; confirm. | Both venues appear under Resources. | |
| 15.5 | Export users, venues, vehicles, facilities. | Each downloads; identifiers appear only in the user export. | |
| 15.6 | System → Retention: preview. | Says how many records are older than 7 years (probably none) and what would happen. Nothing is deleted from a preview. | |

## 16. Signing out and session (all)

| # | Step | Expected | Result |
| --- | --- | --- | --- |
| 16.1 | Sign out; press the browser Back button. | The previous page is not shown with your data; you are asked to sign in. | |
| 16.2 | Sign in on the phone and the laptop at once. | Both work. | |
| 16.3 | Leave a page open for a day and act on it. | Asked to sign in again; the action is not lost silently (the form comes back). | |

## 17. Things to notice everywhere

Tick each once you have seen it hold across the sections above.

| # | Check | Result |
| --- | --- | --- |
| 17.1 | Text is readable without zooming on a phone. | |
| 17.2 | Headings are Title Case; no heading drifts to the right on a tablet. | |
| 17.3 | Boxes never touch each other; text never hugs a border. | |
| 17.4 | No sentence explains how the software works internally. | |
| 17.5 | Dates and times read the same way everywhere ("Fri 02 Oct 2026, 15:00 to 17:00"). | |
| 17.6 | Every email arrived within about a minute and reads plainly. | |
| 17.7 | Keyboard only: Tab reaches every control, the focused control is visible, Escape closes dialogs. | |

---

## After testing

T3 cancels the remaining UAT bookings with the reason "UAT", sets UAT Room and UAT Car to
inactive, deactivates the throwaway user, and removes the UAT announcement. Send the completed
script, with screenshots of every Fail, to the developer.
