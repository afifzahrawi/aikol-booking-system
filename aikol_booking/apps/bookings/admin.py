from django.contrib import admin

from .models import AcademicTerm, Booking, BookingSeries, KeyHandover, TermBreak


class BreakInline(admin.TabularInline):
    model = TermBreak
    extra = 0


@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date")
    inlines = [BreakInline]


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("booking_reference", "resource", "user", "start_at", "end_at", "status")
    list_filter = ("status", "resource__resource_type")
    search_fields = ("booking_reference", "user__email", "user__full_name", "resource__name")
    date_hierarchy = "start_at"
    # History is not edited from a list screen.
    readonly_fields = ("booking_reference", "created_at", "updated_at")


admin.site.register(BookingSeries)
admin.site.register(KeyHandover)
