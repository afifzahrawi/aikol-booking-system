"""Resource management: authorisation, the two-gate delete, uploads, reordering."""

from __future__ import annotations

import datetime as dt
import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Affiliation, Role, User
from apps.audit.models import AuditLog
from apps.bookings.models import Booking
from apps.resources.models import Facility, ResourceImage, ResourceStatus, Vehicle, Venue
from apps.resources.services import DeletionRefused, delete_resource, reorder_facilities
from apps.resources.validators import validate_image_upload


def make_user(email: str, role: str = Role.USER, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="prototype-password-1",
        full_name=email.split("@")[0].title(),
        phone="03-6196 4000",
        role=role,
        email_verified=True,
        **extra,
    )


def png_bytes(size: tuple[int, int] = (40, 30)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (20, 103, 91)).save(buffer, format="PNG")
    return buffer.getvalue()


class Fixtures(TestCase):
    def setUp(self) -> None:
        self.admin = make_user("admin@demo.aikol.test", Role.ADMINISTRATOR)
        self.approver = make_user("approver@demo.aikol.test", Role.APPROVER)
        self.plain = make_user("plain@demo.aikol.test", Role.USER)
        self.venue = Venue.objects.create(
            code="VEN-1", name="Moot Court", venue_type=Venue.VenueType.MOOT_COURT,
            location="Level 2", capacity=80,
        )
        self.car = Vehicle.objects.create(
            code="CAR-1", name="Kulliyyah Car", registration_number="WAA 1111",
            make="Perodua", model="Bezza", year=2023, seats=5,
            road_tax_expiry=timezone.localdate() + dt.timedelta(days=200),
        )


class AuthorisationTests(Fixtures):
    """Checked in the view and answered with 403 — not by hiding a link."""

    MANAGEMENT = ("manage_venues", "manage_vehicles", "manage_facilities")

    def test_an_anonymous_visitor_is_sent_to_sign_in(self):
        response = self.client.get(reverse("resources:venues"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sign-in/", response["Location"])

    def test_an_ordinary_user_is_refused_the_management_screens(self):
        self.client.force_login(self.plain)
        for name in self.MANAGEMENT:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(f"resources:{name}")).status_code, 403)

    def test_an_approver_is_refused_too(self):
        """An approver decides bookings. That is not the same authority as
        editing the resources themselves."""
        self.client.force_login(self.approver)
        for name in self.MANAGEMENT:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(f"resources:{name}")).status_code, 403)

    def test_an_administrator_is_admitted(self):
        self.client.force_login(self.admin)
        for name in self.MANAGEMENT:
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(f"resources:{name}")).status_code, 200)

    def test_an_ordinary_user_cannot_reach_an_edit_form_by_typing_the_url(self):
        self.client.force_login(self.plain)
        url = reverse("resources:venue_edit", args=[self.venue.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)


class BrowsingTests(Fixtures):
    def test_an_untaxed_car_is_withdrawn_from_the_list(self):
        self.car.road_tax_expiry = timezone.localdate() - dt.timedelta(days=1)
        self.car.save(update_fields=["road_tax_expiry"])
        self.client.force_login(self.plain)
        response = self.client.get(reverse("resources:vehicles"))
        self.assertNotContains(response, "WAA 1111")

    def test_a_requester_is_never_shown_the_road_tax_date(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("resources:detail", args=[self.car.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Road tax expiry")

    def test_an_administrator_is_shown_the_road_tax_date(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("resources:detail", args=[self.car.pk]))
        self.assertContains(response, "Road tax expiry")

    def test_a_deactivated_venue_is_not_browsable(self):
        self.venue.status = ResourceStatus.MAINTENANCE
        self.venue.save(update_fields=["status"])
        self.client.force_login(self.plain)
        self.assertNotContains(self.client.get(reverse("resources:venues")), "Moot Court")

    def test_search_is_applied_in_the_query(self):
        Venue.objects.create(
            code="VEN-2", name="Seminar Room 1", venue_type=Venue.VenueType.SEMINAR,
            location="Level 1", capacity=30,
        )
        self.client.force_login(self.plain)
        response = self.client.get(reverse("resources:venues"), {"q": "seminar"})
        self.assertContains(response, "Seminar Room 1")
        self.assertNotContains(response, "Moot Court")

    def test_every_paginated_list_is_ordered(self):
        """An unordered page can repeat or skip rows at the boundary, and
        `annotate()` silently drops a model's default ordering — which is how
        the management lists lost theirs."""
        import warnings

        self.client.force_login(self.admin)
        for name in ("venues", "vehicles", "manage_venues", "manage_vehicles"):
            with self.subTest(view=name), warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.client.get(reverse(f"resources:{name}"))
                unordered = [w for w in caught if "unordered object_list" in str(w.message)]
                self.assertEqual(unordered, [], f"{name} paginates an unordered queryset")

    def test_pagination_links_keep_the_active_filters(self):
        for i in range(20):
            Venue.objects.create(
                code=f"VEN-P{i}", name=f"Tutorial Room {i}",
                venue_type=Venue.VenueType.DISCUSSION, location="Level 3", capacity=10,
            )
        self.client.force_login(self.plain)
        response = self.client.get(reverse("resources:venues"), {"q": "tutorial"})
        self.assertContains(response, "q=tutorial&amp;page=2")


class DeletionGateTests(Fixtures):
    """Two gates, and they are different gates: intent, then audit."""

    def test_an_active_resource_cannot_be_deleted(self):
        with self.assertRaises(DeletionRefused) as ctx:
            delete_resource(self.venue)
        self.assertIn("must be deactivated", str(ctx.exception))
        self.assertTrue(Venue.objects.filter(pk=self.venue.pk).exists())

    def test_a_deactivated_resource_with_history_cannot_be_deleted(self):
        self.venue.status = ResourceStatus.MAINTENANCE
        self.venue.save(update_fields=["status"])
        Booking.objects.create(
            resource=self.venue, user=self.plain, created_by=self.plain,
            start_at=timezone.now() + dt.timedelta(days=3),
            end_at=timezone.now() + dt.timedelta(days=3, hours=2),
            purpose="History",
        )
        with self.assertRaises(DeletionRefused) as ctx:
            delete_resource(self.venue)
        self.assertIn("1 booking record", str(ctx.exception))
        self.assertTrue(Venue.objects.filter(pk=self.venue.pk).exists())

    def test_a_deactivated_unused_resource_is_deleted(self):
        self.venue.status = ResourceStatus.MAINTENANCE
        self.venue.save(update_fields=["status"])
        delete_resource(self.venue)
        self.assertFalse(Venue.objects.filter(pk=self.venue.pk).exists())

    def test_the_screen_names_the_gate_that_stopped_it(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("resources:delete", args=[self.venue.pk]))
        self.assertContains(response, "is still active")

        self.venue.status = ResourceStatus.MAINTENANCE
        self.venue.save(update_fields=["status"])
        Booking.objects.create(
            resource=self.venue, user=self.plain, created_by=self.plain,
            start_at=timezone.now() + dt.timedelta(days=3),
            end_at=timezone.now() + dt.timedelta(days=3, hours=2),
            purpose="History",
        )
        response = self.client.get(reverse("resources:delete", args=[self.venue.pk]))
        self.assertContains(response, "booking record")
        self.assertNotContains(response, "Delete permanently")

    def test_deleting_writes_to_the_audit_log(self):
        self.venue.status = ResourceStatus.MAINTENANCE
        self.venue.save(update_fields=["status"])
        self.client.force_login(self.admin)
        self.client.post(reverse("resources:delete", args=[self.venue.pk]))
        entry = AuditLog.objects.get(action="RESOURCE_DELETED")
        self.assertEqual(entry.actor, self.admin)
        self.assertIn("Moot Court", entry.description)

    def test_a_post_cannot_bypass_the_gates(self):
        """The confirmation screen refuses, and so does the POST behind it."""
        self.client.force_login(self.admin)
        response = self.client.post(reverse("resources:delete", args=[self.venue.pk]), follow=True)
        self.assertTrue(Venue.objects.filter(pk=self.venue.pk).exists())
        self.assertContains(response, "must be deactivated")


class UploadValidationTests(TestCase):
    """The filename and the Content-Type header are both supplied by whoever is
    uploading. Neither is evidence of anything, so the format is sniffed."""

    def test_a_real_png_is_accepted(self):
        upload = SimpleUploadedFile("photo.png", png_bytes(), content_type="image/png")
        validate_image_upload(upload)

    def test_a_script_renamed_as_a_png_is_refused(self):
        upload = SimpleUploadedFile(
            "photo.png", b"<script>alert(1)</script>", content_type="image/png"
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_image_upload(upload)
        self.assertIn("not a readable image", str(ctx.exception))

    def test_an_svg_is_refused_because_it_can_carry_script(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        upload = SimpleUploadedFile("logo.svg", svg, content_type="image/svg+xml")
        with self.assertRaises(ValidationError):
            validate_image_upload(upload)

    @override_settings(MAX_UPLOAD_BYTES=1024)
    def test_a_file_over_the_limit_is_refused(self):
        upload = SimpleUploadedFile("big.png", png_bytes((400, 400)), content_type="image/png")
        with self.assertRaises(ValidationError) as ctx:
            validate_image_upload(upload)
        self.assertIn("limit is", str(ctx.exception))


class ImageUploadViewTests(Fixtures):
    def test_an_administrator_uploads_a_photograph_and_it_is_renamed(self):
        self.client.force_login(self.admin)
        upload = SimpleUploadedFile("../../evil name.png", png_bytes(), content_type="image/png")
        response = self.client.post(
            reverse("resources:images", args=[self.venue.pk]),
            {"image": upload, "caption": "Front view"},
        )
        self.assertEqual(response.status_code, 302)
        image = ResourceImage.objects.get()
        self.assertNotIn("evil name", image.image.name)
        self.assertTrue(image.image.name.startswith(f"resources/{self.venue.pk}/"))
        image.image.delete(save=False)

    def test_a_bad_upload_is_refused_by_the_view(self):
        self.client.force_login(self.admin)
        bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        response = self.client.post(
            reverse("resources:images", args=[self.venue.pk]), {"image": bad}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ResourceImage.objects.count(), 0)

    def test_an_ordinary_user_cannot_upload(self):
        self.client.force_login(self.plain)
        upload = SimpleUploadedFile("photo.png", png_bytes(), content_type="image/png")
        response = self.client.post(
            reverse("resources:images", args=[self.venue.pk]), {"image": upload}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(ResourceImage.objects.count(), 0)


class FacilityTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.facilities = [
            Facility.objects.create(code=f"f{i}", name=f"Facility {i}", display_order=i)
            for i in range(1, 6)
        ]

    def order(self) -> list[str]:
        return list(Facility.objects.order_by("display_order").values_list("code", flat=True))

    def test_reordering_rewrites_the_whole_column_as_one_to_n(self):
        reorder_facilities([self.facilities[4].pk, self.facilities[0].pk])
        self.assertEqual(self.order()[:2], ["f5", "f1"])
        orders = list(Facility.objects.order_by("display_order").values_list("display_order", flat=True))
        self.assertEqual(orders, list(range(1, 6)), "no gaps and no ties")

    def test_a_facility_absent_from_the_posted_order_keeps_its_place_at_the_end(self):
        """A reorder posted from a filtered table must not silently renumber
        rows it could not see."""
        reorder_facilities([self.facilities[2].pk])
        self.assertEqual(self.order()[0], "f3")
        self.assertEqual(self.order()[1:], ["f1", "f2", "f4", "f5"])

    def test_an_unknown_id_is_refused(self):
        with self.assertRaises(ValidationError):
            reorder_facilities([999999])

    def test_the_reorder_endpoint_needs_an_administrator(self):
        self.client.force_login(self.plain)
        response = self.client.post(
            reverse("resources:facility_reorder"), {"order": f"{self.facilities[1].pk}"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.order()[0], "f1", "the order is untouched")

    def test_an_administrator_reorders_through_the_endpoint(self):
        self.client.force_login(self.admin)
        ids = ",".join(str(f.pk) for f in reversed(self.facilities))
        response = self.client.post(reverse("resources:facility_reorder"), {"order": ids})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.order(), ["f5", "f4", "f3", "f2", "f1"])
        self.assertTrue(AuditLog.objects.filter(action="FACILITY_REORDERED").exists())

    def test_a_new_facility_gets_a_generated_code_and_goes_to_the_end(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("resources:facility_new"),
            {"name": "Hearing Loop", "applies_to": "VENUE", "is_active": "on"},
        )
        facility = Facility.objects.get(name="Hearing Loop")
        self.assertEqual(facility.code, "hearing_loop")
        self.assertEqual(facility.display_order, 6)
        self.assertFalse(facility.is_seeded)

    def test_renaming_never_changes_the_code(self):
        """The code is what imports and saved links refer to. If the display
        name were the key, fixing a spelling mistake would break them."""
        self.client.force_login(self.admin)
        facility = self.facilities[0]
        self.client.post(
            reverse("resources:facility_edit", args=[facility.pk]),
            {"name": "Renamed", "code": "something_else", "applies_to": "VENUE", "is_active": "on"},
        )
        facility.refresh_from_db()
        self.assertEqual(facility.name, "Renamed")
        self.assertEqual(facility.code, "f1")

    def test_a_facility_in_use_cannot_be_deleted(self):
        self.venue.facilities.add(self.facilities[0])
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("resources:facility_delete", args=[self.facilities[0].pk]), follow=True
        )
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(Facility.objects.filter(pk=self.facilities[0].pk).exists())

    def test_an_unused_facility_is_deleted(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("resources:facility_delete", args=[self.facilities[0].pk]))
        self.assertFalse(Facility.objects.filter(pk=self.facilities[0].pk).exists())

    def test_the_form_offers_only_active_facilities_that_apply(self):
        from apps.resources.forms import VehicleForm, VenueForm

        Facility.objects.create(code="gps", name="GPS", applies_to=Facility.AppliesTo.VEHICLE)
        Facility.objects.create(code="wifi", name="Wi-Fi", applies_to=Facility.AppliesTo.BOTH)
        Facility.objects.create(code="old", name="Retired", is_active=False)

        venue_codes = set(VenueForm().fields["facilities"].queryset.values_list("code", flat=True))
        car_codes = set(VehicleForm().fields["facilities"].queryset.values_list("code", flat=True))
        self.assertIn("wifi", venue_codes)
        self.assertIn("wifi", car_codes)
        self.assertNotIn("gps", venue_codes)
        self.assertIn("gps", car_codes)
        self.assertNotIn("old", venue_codes, "a deactivated facility is hidden from the forms")


class ResourceEditTests(Fixtures):
    def test_creating_a_venue_writes_to_the_audit_log(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("resources:venue_new"),
            {
                "code": "VEN-NEW", "name": "Discussion Room 3", "venue_type": "DISCUSSION",
                "location": "Level 3", "floor": "3", "capacity": "12",
                "opens_at": "08:00", "closes_at": "22:00", "description": "",
                "status": ResourceStatus.ACTIVE,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Venue.objects.filter(code="VEN-NEW").exists())
        self.assertTrue(AuditLog.objects.filter(action="VENUE_CREATED").exists())

    def test_a_room_that_closes_before_it_opens_is_refused(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("resources:venue_new"),
            {
                "code": "VEN-BAD", "name": "Backwards", "venue_type": "SEMINAR",
                "location": "Level 1", "capacity": "10",
                "opens_at": "18:00", "closes_at": "09:00", "status": ResourceStatus.ACTIVE,
            },
        )
        self.assertContains(response, "close after it opens")
        self.assertFalse(Venue.objects.filter(code="VEN-BAD").exists())

    def test_the_code_cannot_be_changed_once_set(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("resources:vehicle_edit", args=[self.car.pk]),
            {
                "code": "CAR-CHANGED", "name": "Renamed Car", "registration_number": "WAA 1111",
                "make": "Perodua", "model": "Bezza", "year": "2023", "seats": "5",
                "transmission": "AUTO", "fuel_type": "", "description": "",
                "road_tax_expiry": self.car.road_tax_expiry.isoformat(),
                "status": ResourceStatus.MAINTENANCE,
            },
        )
        self.car.refresh_from_db()
        self.assertEqual(self.car.code, "CAR-1")
        self.assertEqual(self.car.name, "Renamed Car")
        self.assertEqual(self.car.status, ResourceStatus.MAINTENANCE)
