from django.urls import path

from . import views

app_name = "resources"

urlpatterns = [
    # Browsing
    path("rooms/", views.venue_list, name="venues"),
    path("cars/", views.vehicle_list, name="vehicles"),
    path("resource/<int:pk>/", views.resource_detail, name="detail"),
    # Management. Every one of these is administrator-only, checked in the view.
    path("manage/rooms/", views.manage_venues, name="manage_venues"),
    path("manage/rooms/new/", views.venue_edit, name="venue_new"),
    path("manage/rooms/<int:pk>/", views.venue_edit, name="venue_edit"),
    path("manage/cars/", views.manage_vehicles, name="manage_vehicles"),
    path("manage/cars/new/", views.vehicle_edit, name="vehicle_new"),
    path("manage/cars/<int:pk>/", views.vehicle_edit, name="vehicle_edit"),
    path("manage/resource/<int:pk>/delete/", views.resource_delete, name="delete"),
    path("manage/resource/<int:pk>/images/", views.resource_images, name="images"),
    path(
        "manage/resource/<int:pk>/images/<int:image_pk>/remove/",
        views.resource_image_delete,
        name="image_delete",
    ),
    path("manage/facilities/", views.manage_facilities, name="manage_facilities"),
    path("manage/facilities/new/", views.facility_edit, name="facility_new"),
    path("manage/facilities/<int:pk>/", views.facility_edit, name="facility_edit"),
    path("manage/facilities/reorder/", views.facility_reorder, name="facility_reorder"),
    path("manage/facilities/<int:pk>/delete/", views.facility_delete, name="facility_delete"),
]
