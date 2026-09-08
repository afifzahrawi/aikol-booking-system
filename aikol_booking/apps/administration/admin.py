from django.contrib import admin

from .models import SiteContent, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description", "updated_at")
    search_fields = ("key", "description")


@admin.register(SiteContent)
class SiteContentAdmin(admin.ModelAdmin):
    list_display = ("site_name", "organisation", "updated_at")
