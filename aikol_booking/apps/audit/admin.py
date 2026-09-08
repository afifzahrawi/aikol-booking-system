from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Append-only. The admin may read it and nothing more."""

    list_display = ("created_at", "actor_email", "action", "entity_type", "entity_id")
    list_filter = ("action", "entity_type")
    search_fields = ("actor_email", "action", "description")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
