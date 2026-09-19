# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary users are IIUM students, lecturers and staff who need to reserve an AIKOL room or
Kulliyyah car from a phone or desktop. Members of the public may also register and request a
booking. Approvers decide requests; Kulliyyah administrators manage bookings, resources, academic
calendars, users, key custody, reports and published site content.

## Product Purpose

The system replaces fragmented booking records with one dependable place to find a resource,
request it, receive a decision and preserve the operational record. Success means a requester can
make a valid request quickly, staff can see what needs attention, no active bookings overlap, and
the full approval and key-custody history remains auditable.

## Positioning

One booking timeline governs rooms and vehicles while still handling their real differences:
semester recurrence for rooms, multi-day trips and driver approval for cars, and accountable key
handover for both.

## Operating Context

Requesters commonly check availability before a class, meeting, event or trip. Administrators work
from queues: pending decisions, keys awaiting collection or return, resources needing maintenance,
and records requiring export. Some work happens at a counter while another person collects or
returns the key. Mobile use is a first-class case, not a reduced desktop fallback.

## Capabilities and Constraints

- Own Django authentication; no IIUM SSO. Email is the login identifier.
- Public self-registration is supported. IIUM members provide a matriculation or staff number;
  public users explicitly identify themselves as non-IIUM.
- Venues and cars share conflict prevention. Pending and approved requests reserve their periods.
- Every booking requires one Kulliyyah booking decision. VMU-driver vehicle requests also require
  management approval.
- Venue bookings are within 08:00–22:00 and at most nine hours. Vehicle trips may span days.
- Users may cancel their own bookings at least 72 hours before the booking date with a mandatory
  reason. Administrators handle exceptions.
- Weekly room series use one of multiple academic calendars and omit dates outside teaching periods
  and inside configured breaks.
- Administrators can book on behalf of another user, manage resource images and facilities, edit
  login/home imagery and introduction copy, and publish scheduled announcements.
- Signed-in users can maintain their own name, email address and telephone number. Changing the
  email pauses booking until the new address is verified; governed identity, affiliation and role
  fields remain under Kulliyyah office control.
- Used users, resources and bookings are deactivated or cancelled rather than erased. Unused
  resources may be deleted only after deactivation.
- Booking records are retained for seven years and exported before removal.
- Django templates and vendored assets remain the implementation model. No JavaScript application
  framework or CDN dependency is introduced.

## Brand Commitments

The product represents Ahmad Ibrahim Kulliyyah of Laws and International Islamic University
Malaysia. The IIUM mark appears first and the AIKOL mark second. Both are editable by an
administrator. The interface must feel credible for a university office without repeating the old
prototype's page composition or treating complex features as disposable. The requested redesign
keeps the use cases but replaces the incumbent visual style.

## Evidence on Hand

- Confirmed requirements and decisions are recorded in `CLAUDE.md` and the local-only management
  source document.
- The working Django application and 297-test regression suite are the behavioral authority.
- Existing institutional marks are in `aikol_booking/static/images/`.
- The supplied building photograph and generated room/vehicle placeholders are development assets;
  administrators can replace public-facing imagery through the application.
- Demonstration names, bookings and announcements are fictional and labelled as such.

## Product Principles

1. Make the next operational action obvious without hiding available capability.
2. Preserve context from search through request, decision and handover.
3. Prevent invalid or conflicting states before asking users to recover from them.
4. Separate roles and responsibilities while keeping one coherent resource timeline.
5. Keep records trustworthy, searchable and explainable.

## Accessibility & Inclusion

The responsive site supports keyboard and screen-reader use, visible focus, labelled controls,
meaning beyond colour, and touch targets of at least 44 pixels. It must remain usable from 320-pixel
phone widths through desktop screens and at browser zoom. Public users must not be presented as an
error case or forced through IIUM-only terminology.
