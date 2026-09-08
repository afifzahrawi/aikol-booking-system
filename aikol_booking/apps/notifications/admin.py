from django.contrib import admin

from .models import EmailOutbox


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "to_address", "status", "attempts", "sent_at")
    list_filter = ("status", "kind")
    search_fields = ("to_address", "subject")
