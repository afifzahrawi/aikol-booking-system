from django.apps import AppConfig


class AdministrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.administration"
    label = "administration"

    def ready(self) -> None:
        # Any save or delete of a row the shared page furniture reads clears
        # the in-process memory, so an edit or a decision shows on the next
        # page rather than after the memory expires.
        from django.db.models.signals import post_delete, post_save

        from apps.bookings.models import Booking, KeyHandover
        from apps.notifications.models import EmailConfiguration

        from .memo import forget
        from .models import SiteContent, SystemSetting

        for model in (SiteContent, SystemSetting, EmailConfiguration, Booking, KeyHandover):
            post_save.connect(forget, sender=model, dispatch_uid=f"memo-save-{model.__name__}")
            post_delete.connect(forget, sender=model, dispatch_uid=f"memo-del-{model.__name__}")
