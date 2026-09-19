from django.contrib import admin

from .models import EmailConfiguration, EmailOutbox


@admin.register(EmailConfiguration)
class EmailConfigurationAdmin(admin.ModelAdmin):
    list_display = ("host", "port", "username", "is_active", "updated_at")
    readonly_fields = ("encrypted_password",)


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "to_address", "status", "attempts", "sent_at")
    list_filter = ("status", "kind")
    search_fields = ("to_address", "subject")
