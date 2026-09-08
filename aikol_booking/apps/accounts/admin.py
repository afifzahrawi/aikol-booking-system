from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("full_name",)
    list_display = ("full_name", "email", "identification_number", "role", "affiliation",
                    "email_verified", "is_active")
    list_filter = ("role", "affiliation", "email_verified", "is_active")
    search_fields = ("full_name", "email", "identification_number")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Person", {"fields": ("full_name", "identification_number", "phone", "affiliation")}),
        ("Driving licence", {"fields": ("licence_number", "licence_expiry")}),
        ("Authority", {"fields": ("role", "is_active", "is_staff", "is_superuser",
                                  "groups", "user_permissions")}),
        ("Verification", {"fields": ("email_verified", "email_verified_at", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "phone", "affiliation", "password1", "password2"),
        }),
    )
    readonly_fields = ("email_verified_at", "date_joined")
