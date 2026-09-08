from django.contrib import admin

from .models import Facility, ResourceImage, Venue, Vehicle


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "applies_to", "display_order", "is_active", "is_seeded")
    list_filter = ("applies_to", "is_active", "is_seeded")
    search_fields = ("name", "code")


class ImageInline(admin.TabularInline):
    model = ResourceImage
    extra = 0


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "venue_type", "location", "capacity", "status")
    list_filter = ("venue_type", "status")
    search_fields = ("name", "code", "location")
    inlines = [ImageInline]


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "registration_number", "seats", "road_tax_expiry", "status")
    list_filter = ("status", "transmission")
    search_fields = ("name", "code", "registration_number")
    inlines = [ImageInline]
