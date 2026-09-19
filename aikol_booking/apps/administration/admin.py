from django.contrib import admin

from .models import Announcement, SiteContent, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description", "updated_at")
    search_fields = ("key", "description")


@admin.register(SiteContent)
class SiteContentAdmin(admin.ModelAdmin):
    list_display = ("site_name", "organisation", "updated_at")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "tone", "is_active", "starts_at", "ends_at", "updated_at")
    list_filter = ("tone", "is_active")
    search_fields = ("title", "message")
