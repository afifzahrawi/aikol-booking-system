"""Venue types the Admin maintains, 4:3 venue photographs, and the dashboard summary."""

from __future__ import annotations

import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.resources.models import ResourceImage, Venue, VenueType
from apps.resources.services import fit_venue_photo

from .test_management import Fixtures, png_bytes

MEDIA = tempfile.mkdtemp()


class VenueTypeTests(Fixtures):
    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.admin)

    def test_the_six_original_types_are_seeded(self):
        self.assertEqual(VenueType.objects.filter(is_seeded=True).count(), 6)
        self.assertEqual(self.venue.get_venue_type_display(), "Moot court")

    def test_the_admin_adds_a_type_and_it_reaches_the_venue_form(self):
        response = self.client.post(
            reverse("resources:venue_type_new"), {"name": "Computer lab", "is_active": "True"}
        )
        self.assertEqual(response.status_code, 302)
        kind = VenueType.objects.get(name="Computer lab")
        self.assertEqual(kind.code, "COMPUTER_LAB")
        self.assertTrue(AuditLog.objects.filter(action="VENUE_TYPE_CREATED").exists())
        form = self.client.get(reverse("resources:venue_new"))
        self.assertContains(form, "Computer lab")

    def test_renaming_keeps_the_code_and_the_venues(self):
        kind = VenueType.objects.get(code="MOOT_COURT")
        self.client.post(
            reverse("resources:venue_type_edit", args=[kind.pk]),
            {"name": "Moot courtroom", "is_active": "True"},
        )
        self.venue.refresh_from_db()
        self.assertEqual(self.venue.venue_type_id, "MOOT_COURT")
        self.assertEqual(self.venue.get_venue_type_display(), "Moot courtroom")

    def test_a_type_in_use_cannot_be_deleted(self):
        kind = VenueType.objects.get(code="MOOT_COURT")
        self.client.post(reverse("resources:venue_type_delete", args=[kind.pk]))
        self.assertTrue(VenueType.objects.filter(pk=kind.pk).exists())

    def test_an_unused_type_can_be_deleted(self):
        kind = VenueType.objects.get(code="LECTURE")
        self.client.post(reverse("resources:venue_type_delete", args=[kind.pk]))
        self.assertFalse(VenueType.objects.filter(pk=kind.pk).exists())

    def test_a_withdrawn_type_leaves_the_filter(self):
        VenueType.objects.filter(code="LECTURE").update(is_active=False)
        page = self.client.get(reverse("resources:venues"))
        self.assertNotContains(page, "Lecture room")
        self.assertContains(page, "Moot court")

    def test_only_the_admin_manages_types(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(reverse("resources:manage_venue_types")).status_code, 403)


@override_settings(MEDIA_ROOT=MEDIA)
class VenuePhotoTests(Fixtures):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_any_shape_becomes_1600_by_1200(self):
        from PIL import Image

        for size in [(400, 900), (3000, 1000), (800, 600)]:
            upload = SimpleUploadedFile("p.png", png_bytes(size), content_type="image/png")
            fitted = fit_venue_photo(upload)
            with Image.open(io.BytesIO(fitted.read())) as image:
                self.assertEqual(image.size, (1600, 1200))
                self.assertEqual(image.format, "JPEG")

    def test_a_venue_upload_is_stored_at_4_by_3(self):
        from PIL import Image

        self.client.force_login(self.admin)
        upload = SimpleUploadedFile("tall.png", png_bytes((300, 900)), content_type="image/png")
        self.client.post(reverse("resources:images", args=[self.venue.pk]), {"images": upload})
        stored = ResourceImage.objects.get(resource=self.venue)
        with Image.open(stored.image.path) as image:
            self.assertEqual(image.size, (1600, 1200))

    def test_the_upload_screen_offers_the_crop_for_venues_only(self):
        self.client.force_login(self.admin)
        venue = self.client.get(reverse("resources:images", args=[self.venue.pk]))
        car = self.client.get(reverse("resources:images", args=[self.car.pk]))
        self.assertContains(venue, "image-crop.js")
        self.assertNotContains(car, "image-crop.js")


class DashboardSummaryTests(Fixtures):
    def test_the_admin_has_no_booking_summary(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, "Up Next")

    def test_a_requester_keeps_it(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "Up Next")
