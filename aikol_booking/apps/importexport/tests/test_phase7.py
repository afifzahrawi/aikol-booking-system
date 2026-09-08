"""Bulk import, export, reporting and retention."""

from __future__ import annotations

import csv
import datetime as dt
import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.administration import retention
from apps.administration.models import SystemSetting
from apps.audit.models import AuditLog
from apps.bookings.models import Booking, BookingArchive, BookingStatus, KeyHandover
from apps.importexport.services import apply_plan, validate
from apps.reporting import services as reporting
from apps.resources.models import Facility, Resource, Vehicle, Venue


def make_user(email: str, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name=extra.pop("full_name", email.split("@")[0].title()),
        phone="012-345 6789",
        email_verified=True,
        **extra,
    )


def upload(text: str, name: str = "data.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class Fixtures(TestCase):
    def setUp(self) -> None:
        SystemSetting.seed()
        self.admin = make_user("admin@demo.aikol.test", role=Role.ADMINISTRATOR)
        self.approver = make_user("approver@demo.aikol.test", role=Role.APPROVER)
        self.plain = make_user("plain@demo.aikol.test")
        Facility.objects.create(code="projector", name="Projector", applies_to="VENUE")
        Facility.objects.create(code="aircond", name="Air Conditioning", applies_to="BOTH")
        Facility.objects.create(code="gps", name="GPS", applies_to="VEHICLE")


class HeaderTests(Fixtures):
    def test_a_missing_column_rejects_the_whole_file(self):
        """Validating rows against a header we do not understand would produce
        misleading per-row errors."""
        plan = validate("facilities", upload("code,name\nx,Thing\n"))
        self.assertTrue(plan.file_errors)
        self.assertIn("applies_to", plan.file_errors[0])
        self.assertEqual(plan.rows, [])

    def test_an_empty_file_is_reported(self):
        plan = validate("facilities", upload(""))
        self.assertIn("empty", plan.file_errors[0])

    def test_a_row_with_the_wrong_number_of_values_is_a_row_error(self):
        plan = validate(
            "facilities", upload("code,name,applies_to,status\na,B,Venue,Active,extra\n")
        )
        self.assertEqual(len(plan.invalid), 1)
        self.assertIn("the header has 4", plan.invalid[0].errors[0])

    @override_settings()
    def test_a_file_over_the_limit_is_refused(self):
        from apps.importexport import services

        big = upload("code,name,applies_to,status\n")
        big.size = 11 * 1024 * 1024
        plan = validate("facilities", big)
        self.assertIn("limit is 10 MB", plan.file_errors[0])


class FacilityImportTests(Fixtures):
    HEADER = "code,name,applies_to,status\n"

    def test_a_clean_file_imports(self):
        plan = validate(
            "facilities", upload(self.HEADER + "hearing_loop,Hearing Loop,Venue,Active\n")
        )
        self.assertEqual(len(plan.valid), 1)
        summary = apply_plan(plan)
        self.assertEqual(summary["created"], 1)
        self.assertTrue(Facility.objects.filter(code="hearing_loop").exists())

    def test_re_importing_an_existing_code_updates_rather_than_fails(self):
        """The one template where that is true: a facility list is maintained,
        not loaded once, and the code is the identity resources already link
        to."""
        plan = validate("facilities", upload(self.HEADER + "projector,Data Projector,Venue,Active\n"))
        self.assertEqual(len(plan.valid), 1)
        self.assertIn("will be updated", plan.valid[0].warnings[0])
        summary = apply_plan(plan)
        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(Facility.objects.get(code="projector").name, "Data Projector")

    def test_a_duplicate_within_the_file_is_caught(self):
        """The database cannot catch this one — neither row exists yet."""
        plan = validate(
            "facilities",
            upload(self.HEADER + "loop,Loop,Venue,Active\nloop,Loop Again,Venue,Active\n"),
        )
        self.assertEqual(len(plan.invalid), 1)
        self.assertIn("more than once in this file", plan.invalid[0].errors[0])

    def test_a_bad_applies_to_is_reported(self):
        plan = validate("facilities", upload(self.HEADER + "x,Thing,Aeroplane,Active\n"))
        self.assertIn("applies_to must be", " ".join(plan.invalid[0].errors))


class UserImportTests(Fixtures):
    HEADER = "name,email,identification_number,phone,affiliation,role,status\n"

    def row(self, **o):
        d = {
            "name": "Nurul Test", "email": "nurul@live.iium.edu.my",
            "identification_number": "2117001", "phone": "012-345 6789",
            "affiliation": "Student", "role": "User", "status": "Active",
        }
        d.update(o)
        return ",".join(d[k] for k in
                        ["name", "email", "identification_number", "phone",
                         "affiliation", "role", "status"]) + "\n"

    def test_a_clean_row_imports_unverified_with_no_usable_password(self):
        """Setting a password through the activation link verifies the address,
        so an imported user follows the same proof-of-mailbox path as somebody
        who registered themselves."""
        plan = validate("users", upload(self.HEADER + self.row()))
        apply_plan(plan)
        person = User.objects.get(email="nurul@live.iium.edu.my")
        self.assertFalse(person.email_verified)
        self.assertFalse(person.has_usable_password())
        self.assertFalse(person.can_book)

    def test_an_imported_account_is_told_how_to_activate(self):
        from apps.notifications.models import EmailOutbox

        apply_plan(validate("users", upload(self.HEADER + self.row())))
        row = EmailOutbox.objects.get(kind="ACCOUNT_IMPORTED")
        self.assertEqual(row.to_address, "nurul@live.iium.edu.my")
        self.assertIn("Forgotten your password", row.body)

    def test_a_non_iium_address_is_refused(self):
        plan = validate("users", upload(self.HEADER + self.row(email="x@gmail.com")))
        self.assertIn("not an IIUM address", " ".join(plan.invalid[0].errors))

    def test_an_existing_address_is_refused(self):
        plan = validate("users", upload(self.HEADER + self.row(email=self.admin.email)))
        self.assertIn("already exists", " ".join(plan.invalid[0].errors))

    def test_a_missing_identification_number_is_refused(self):
        plan = validate("users", upload(self.HEADER + self.row(identification_number="")))
        self.assertIn("identification_number is required", " ".join(plan.invalid[0].errors))

    def test_every_reason_is_reported_at_once(self):
        """So the spreadsheet can be corrected in one pass rather than one
        problem per upload."""
        plan = validate(
            "users",
            upload(self.HEADER + self.row(
                email="not-an-email", identification_number="", phone="",
                affiliation="Wizard", role="Sorcerer")),
        )
        errors = " ".join(plan.invalid[0].errors)
        for expected in ("valid email", "identification_number", "phone", "affiliation", "role"):
            self.assertIn(expected, errors)

    def test_the_template_has_no_password_column(self):
        from apps.importexport.services import TEMPLATES

        self.assertNotIn("password", TEMPLATES["users"])
        self.assertFalse([c for c in TEMPLATES["users"] if "licence" in c])


class ResourceImportTests(Fixtures):
    VENUE_HEADER = ("code,name,building,floor,venue_type,capacity,facilities,"
                    "bookable_window_start,bookable_window_end\n")
    VEHICLE_HEADER = ("code,name,registration_number,vehicle_class,make,model,year,seats,"
                      "transmission,fuel_type,facilities,road_tax_expiry\n")

    def test_venues_import_through_the_two_step_bulk_insert(self):
        """bulk_create and multi-table inheritance do not mix: the parent rows
        go in first, then the children against the returned keys."""
        rows = "".join(
            f"VEN-{i},Room {i},Main,1,Seminar room,30,projector|aircond,08:00,22:00\n"
            for i in range(1, 4)
        )
        plan = validate("venues", upload(self.VENUE_HEADER + rows))
        self.assertEqual(len(plan.valid), 3)
        apply_plan(plan)
        self.assertEqual(Venue.objects.count(), 3)
        self.assertEqual(Resource.objects.count(), 3)
        self.assertEqual(
            set(Venue.objects.get(code="VEN-1").facilities.values_list("code", flat=True)),
            {"projector", "aircond"},
        )

    def test_a_venue_cannot_take_a_code_a_vehicle_already_holds(self):
        Vehicle.objects.create(
            code="SHARED", name="Car", registration_number="WAA 1",
            make="P", model="B", year=2020, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=100),
        )
        plan = validate(
            "venues",
            upload(self.VENUE_HEADER + "SHARED,Room,Main,1,Seminar room,30,,08:00,22:00\n"),
        )
        self.assertIn("already in use", " ".join(plan.invalid[0].errors))
        self.assertIn("share one namespace", " ".join(plan.invalid[0].errors))

    def test_an_unknown_facility_code_is_an_error_not_a_silent_creation(self):
        """A typo must not quietly add 'projecter' to the facility list for
        everyone who books afterwards."""
        plan = validate(
            "venues",
            upload(self.VENUE_HEADER + "VEN-9,Room,Main,1,Seminar room,30,projecter,08:00,22:00\n"),
        )
        self.assertIn("does not exist", " ".join(plan.invalid[0].errors))
        self.assertFalse(Facility.objects.filter(code="projecter").exists())

    def test_a_facility_that_does_not_apply_is_refused(self):
        plan = validate(
            "venues",
            upload(self.VENUE_HEADER + "VEN-9,Room,Main,1,Seminar room,30,gps,08:00,22:00\n"),
        )
        self.assertIn("does not apply", " ".join(plan.invalid[0].errors))

    def test_blank_times_inherit_the_confirmed_window(self):
        plan = validate(
            "venues", upload(self.VENUE_HEADER + "VEN-9,Room,Main,1,Seminar room,30,,,\n")
        )
        apply_plan(plan)
        venue = Venue.objects.get(code="VEN-9")
        self.assertEqual(venue.opens_at, dt.time(8, 0))
        self.assertEqual(venue.closes_at, dt.time(22, 0))

    def test_an_expired_road_tax_is_a_warning_not_an_error(self):
        """An administrator may be loading a fleet mid-renewal. The car is
        imported; it simply cannot be booked until the date is updated."""
        past = (timezone.localdate() - dt.timedelta(days=30)).isoformat()
        plan = validate(
            "vehicles",
            upload(self.VEHICLE_HEADER + f"CAR-1,Car,WAA 1,Car,Proton,Saga,2022,5,Auto,Petrol,gps,{past}\n"),
        )
        self.assertEqual(len(plan.valid), 1)
        self.assertIn("cannot be booked", plan.valid[0].warnings[0])
        apply_plan(plan)
        car = Vehicle.objects.get(code="CAR-1")
        self.assertFalse(car.is_bookable)

    def test_a_vehicle_class_other_than_car_is_refused(self):
        future = (timezone.localdate() + dt.timedelta(days=300)).isoformat()
        plan = validate(
            "vehicles",
            upload(self.VEHICLE_HEADER + f"BUS-1,Bus,WAA 2,Bus,Scania,X,2019,40,Manual,Diesel,,{future}\n"),
        )
        self.assertIn("must be Car", " ".join(plan.invalid[0].errors))

    def test_nothing_is_written_by_validation(self):
        plan = validate(
            "venues", upload(self.VENUE_HEADER + "VEN-9,Room,Main,1,Seminar room,30,,08:00,22:00\n")
        )
        self.assertEqual(len(plan.valid), 1)
        self.assertEqual(Venue.objects.count(), 0, "the preview writes nothing")


class ImportViewTests(Fixtures):
    def test_only_an_administrator_reaches_data_management(self):
        self.client.force_login(self.plain)
        self.assertEqual(
            self.client.get(reverse("importexport:data_management")).status_code, 403
        )
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("importexport:data_management")).status_code, 200
        )

    def test_upload_then_confirm_imports_and_logs(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("importexport:data_management"),
            {"kind": "facilities",
             "csv_file": upload("code,name,applies_to,status\nloop,Hearing Loop,Venue,Active\n")},
        )
        self.assertFalse(Facility.objects.filter(code="loop").exists(), "preview writes nothing")
        self.client.post(reverse("importexport:confirm"))
        self.assertTrue(Facility.objects.filter(code="loop").exists())
        self.assertTrue(AuditLog.objects.filter(action="BULK_IMPORT").exists())

    def test_confirming_with_nothing_uploaded_is_refused(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("importexport:confirm"), follow=True)
        self.assertContains(response, "nothing waiting to be imported")

    def test_the_template_download_carries_the_expected_columns(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("importexport:template", args=["venues"]))
        self.assertIn("code,name,building", response.content.decode())


class ExportTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.venue = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        self.venue.facilities.add(Facility.objects.get(code="projector"))
        self.plain.identification_number = "2117001"
        self.plain.save(update_fields=["identification_number"])
        Booking.objects.create(
            resource=self.venue, user=self.plain, created_by=self.plain,
            start_at=timezone.now() + dt.timedelta(days=3),
            end_at=timezone.now() + dt.timedelta(days=3, hours=2),
            purpose="Tutorial", status=BookingStatus.APPROVED,
        )

    def body(self, response) -> str:
        return b"".join(response.streaming_content).decode()

    def test_no_export_carries_a_password_hash(self):
        self.client.force_login(self.admin)
        for name in ("export_users", "export_venues", "export_vehicles", "export_facilities"):
            with self.subTest(export=name):
                text = self.body(self.client.get(reverse(f"importexport:{name}")))
                self.assertNotIn("pbkdf2", text)
                self.assertNotIn("password", text.lower())

    def test_personal_identifiers_appear_only_in_the_user_export(self):
        self.client.force_login(self.admin)
        users = self.body(self.client.get(reverse("importexport:export_users")))
        self.assertIn("2117001", users)
        self.assertIn("012-345 6789", users)

        bookings = self.body(self.client.get(reverse("importexport:export_bookings")))
        self.assertNotIn("2117001", bookings)
        self.assertNotIn("012-345 6789", bookings)

    def test_a_venue_export_can_be_re_imported_without_translation(self):
        self.client.force_login(self.admin)
        text = self.body(self.client.get(reverse("importexport:export_venues")))
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[1][rows[0].index("facilities")], "projector")

    def test_an_ordinary_user_cannot_export_bookings(self):
        self.client.force_login(self.plain)
        self.assertEqual(
            self.client.get(reverse("importexport:export_bookings")).status_code, 403
        )

    def test_an_approver_can(self):
        self.client.force_login(self.approver)
        self.assertEqual(
            self.client.get(reverse("importexport:export_bookings")).status_code, 200
        )

    def test_every_export_is_written_to_the_audit_log(self):
        self.client.force_login(self.admin)
        self.body(self.client.get(reverse("importexport:export_users")))
        self.assertTrue(AuditLog.objects.filter(action="DATA_EXPORTED").exists())


class ReportingTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.venue = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        self.car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1",
            make="P", model="B", year=2022, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=300),
        )
        # A Wednesday, 09:00-12:00: three room-hours across three cells.
        base = timezone.localdate() - dt.timedelta(days=7)
        self.day = base - dt.timedelta(days=(base.weekday() - 2) % 7)
        self.booking = Booking.objects.create(
            resource=self.venue, user=self.plain, created_by=self.plain,
            start_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(9, 0))),
            end_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(12, 0))),
            purpose="Tutorial", status=BookingStatus.APPROVED,
        )

    def heat(self):
        bookings = reporting.period_bookings(
            timezone.localdate() - dt.timedelta(days=30), timezone.localdate()
        )
        return reporting.demand_heatmap(bookings)

    def test_a_booking_is_spread_across_the_hours_it_occupies(self):
        heat = self.heat()
        row = heat["rows"][self.day.weekday()]
        by_hour = {c["hour"]: c["value"] for c in row["cells"]}
        self.assertEqual(by_hour[9], 1.0)
        self.assertEqual(by_hour[10], 1.0)
        self.assertEqual(by_hour[11], 1.0)
        self.assertEqual(by_hour[13], 0.0)
        self.assertEqual(heat["total"], 3.0)

    def test_a_part_hour_counts_as_a_fraction(self):
        """Otherwise a 30-minute booking and a 3-hour one look the same."""
        Booking.objects.create(
            resource=self.venue, user=self.admin, created_by=self.admin,
            start_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(14, 0))),
            end_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(14, 30))),
            purpose="Short", status=BookingStatus.APPROVED,
        )
        row = self.heat()["rows"][self.day.weekday()]
        self.assertEqual({c["hour"]: c["value"] for c in row["cells"]}[14], 0.5)

    def test_an_empty_hour_is_level_zero_not_the_palest_step(self):
        """'Nobody booked this' and 'one person booked this' differ in kind."""
        row = self.heat()["rows"][self.day.weekday()]
        by_hour = {c["hour"]: c["level"] for c in row["cells"]}
        self.assertEqual(by_hour[13], 0)
        self.assertGreaterEqual(by_hour[9], 1)

    def test_vehicles_are_excluded_from_the_heatmap(self):
        """A trip that runs overnight has no meaningful hour of day."""
        Booking.objects.create(
            resource=self.car, user=self.plain, created_by=self.plain,
            start_at=timezone.make_aware(dt.datetime.combine(self.day, dt.time(8, 0))),
            end_at=timezone.make_aware(
                dt.datetime.combine(self.day + dt.timedelta(days=2), dt.time(17, 0))
            ),
            purpose="Outstation", status=BookingStatus.APPROVED,
        )
        self.assertEqual(self.heat()["total"], 3.0, "unchanged by the car")

    def test_a_pending_booking_is_not_counted_as_demand(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=["status"])
        self.assertEqual(self.heat()["total"], 0.0)

    def test_the_requester_table_carries_no_personal_identifiers(self):
        bookings = reporting.period_bookings(
            timezone.localdate() - dt.timedelta(days=30), timezone.localdate()
        )
        rows = reporting.frequent_requesters(bookings)
        self.assertEqual(rows[0]["name"], self.plain.full_name)
        self.assertEqual(set(rows[0]), {"name", "affiliation", "count"})

    def test_only_an_approver_or_administrator_reads_reports(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(reverse("reporting:reports")).status_code, 403)
        self.client.force_login(self.approver)
        self.assertEqual(self.client.get(reverse("reporting:reports")).status_code, 200)

    def test_the_screen_renders_the_grid(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reporting:reports"))
        self.assertContains(response, "Room demand by hour and day")
        self.assertContains(response, 'data-level=')


class RetentionTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.venue = Venue.objects.create(
            code="VEN-1", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        self.old = []
        for i in range(3):
            when = timezone.now() - dt.timedelta(days=365 * 8 + i)
            booking = Booking.objects.create(
                resource=self.venue, user=self.plain, created_by=self.plain,
                start_at=when, end_at=when + dt.timedelta(hours=2),
                purpose="Ancient history", status=BookingStatus.COMPLETED,
            )
            self.old.append(booking)
        KeyHandover.objects.create(
            booking=self.old[0], issued_at=self.old[0].start_at, issued_by=self.admin,
            collected_by_name="Aiman", returned_at=self.old[0].end_at, returned_to=self.admin,
        )
        self.recent = Booking.objects.create(
            resource=self.venue, user=self.plain, created_by=self.plain,
            start_at=timezone.now() - dt.timedelta(days=30),
            end_at=timezone.now() - dt.timedelta(days=30) + dt.timedelta(hours=2),
            purpose="Last month", status=BookingStatus.COMPLETED,
        )

    def tearDown(self) -> None:
        import shutil

        if retention.EXPORT_DIR.exists():
            shutil.rmtree(retention.EXPORT_DIR, ignore_errors=True)

    def test_the_preview_changes_nothing(self):
        before = Booking.objects.count()
        preview = retention.preview()
        self.assertEqual(preview.bookings, 3)
        self.assertEqual(preview.handovers, 1)
        self.assertEqual(Booking.objects.count(), before)

    def test_a_wrong_confirmation_phrase_deletes_nothing(self):
        with self.assertRaises(ValidationError) as ctx:
            retention.run_cleanup(actor=self.admin, confirmation="yes")
        self.assertIn("Nothing has been deleted", str(ctx.exception))
        self.assertEqual(Booking.objects.count(), 4)

    def test_a_non_administrator_cannot_run_it(self):
        with self.assertRaises(ValidationError):
            retention.run_cleanup(actor=self.approver, confirmation=retention.TYPED_CONFIRMATION)
        self.assertEqual(Booking.objects.count(), 4)

    def test_permanent_deletion_with_no_copy_is_not_offered(self):
        with self.assertRaises(ValidationError) as ctx:
            retention.run_cleanup(
                actor=self.admin, confirmation=retention.TYPED_CONFIRMATION, action="DELETE"
            )
        self.assertIn("restricted", str(ctx.exception))
        self.assertEqual(Booking.objects.count(), 4)

    def test_export_then_delete_writes_a_verified_file(self):
        summary = retention.run_cleanup(
            actor=self.admin, confirmation=retention.TYPED_CONFIRMATION, action="EXPORT"
        )
        self.assertEqual(summary["removed"], 3)
        self.assertEqual(Booking.objects.count(), 1, "the recent booking is untouched")
        self.assertEqual(Booking.objects.get().pk, self.recent.pk)

        path = retention.EXPORT_DIR / summary["path"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows) - 1, 3, "the file holds exactly what was removed")
        self.assertIn("Ancient history", rows[1])

    def test_key_records_go_before_the_bookings_they_belong_to(self):
        """PROTECT means a cleanup that forgot them would simply fail rather
        than orphan anything."""
        retention.run_cleanup(
            actor=self.admin, confirmation=retention.TYPED_CONFIRMATION, action="EXPORT"
        )
        self.assertEqual(KeyHandover.objects.count(), 0)

    def test_the_archive_action_keeps_a_denormalised_copy(self):
        retention.run_cleanup(
            actor=self.admin, confirmation=retention.TYPED_CONFIRMATION, action="ARCHIVE"
        )
        self.assertEqual(BookingArchive.objects.count(), 3)
        archived = BookingArchive.objects.first()
        # It survives the live tables: the email and the resource code are text.
        self.assertEqual(archived.user_email, self.plain.email)
        self.assertEqual(archived.resource_code, "VEN-1")

    def test_the_run_is_written_to_the_audit_log(self):
        retention.run_cleanup(actor=self.admin, confirmation=retention.TYPED_CONFIRMATION)
        entry = AuditLog.objects.get(action="RETENTION_CLEANUP")
        self.assertIn("3 records", entry.description)

    def test_the_screen_needs_the_typed_phrase(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("administration:retention"), {"confirmation": "ok"}, follow=True
        )
        self.assertContains(response, "Nothing has been deleted")
        self.assertEqual(Booking.objects.count(), 4)

    def test_an_ordinary_user_cannot_reach_the_screen(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(reverse("administration:retention")).status_code, 403)
