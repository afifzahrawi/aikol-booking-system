from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from .maintenance import run_maintenance

urlpatterns = [
    path("internal/maintenance/<str:task>/", run_maintenance, name="maintenance-task"),
    # Django's admin has a sign-in form of its own, outside the rate limit and
    # the second factor's flow. Everybody signs in through the application's.
    path("admin/login/", RedirectView.as_view(url="/sign-in/?next=/admin/", permanent=False)),
    path("admin/", admin.site.urls),
    path("", include("apps.administration.urls")),
    path("", include("apps.importexport.urls")),
    path("", include("apps.reporting.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.resources.urls")),
    path("", include("apps.accounts.urls")),
]

# In development Django serves uploaded images. In production Nginx does, and
# this block is inert because DEBUG is False.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
