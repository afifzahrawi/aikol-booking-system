from django.urls import path

from . import views

app_name = "importexport"

urlpatterns = [
    path("manage/data/", views.data_management, name="data_management"),
    path("manage/data/confirm/", views.confirm_import, name="confirm"),
    path("manage/data/template/<str:kind>/", views.template_csv, name="template"),
    path("manage/export/users/", views.export_users, name="export_users"),
    path("manage/export/venues/", views.export_venues, name="export_venues"),
    path("manage/export/vehicles/", views.export_vehicles, name="export_vehicles"),
    path("manage/export/facilities/", views.export_facilities, name="export_facilities"),
    path("export/bookings/", views.export_bookings, name="export_bookings"),
]
