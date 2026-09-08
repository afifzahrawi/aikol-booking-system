from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("bookings/", views.my_bookings, name="mine"),
    path("bookings/<int:pk>/", views.booking_detail, name="detail"),
    path("bookings/<int:pk>/cancel/", views.booking_cancel, name="cancel"),
    path("series/<int:pk>/cancel/", views.series_cancel, name="series_cancel"),
    path("resource/<int:pk>/availability/", views.availability, name="availability"),
    path("resource/<int:pk>/book/", views.booking_create, name="create"),
    path("resource/<int:pk>/book/weekly/", views.series_create, name="series_create"),
    # Deciding is the approver's authority, checked in the view.
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/<int:pk>/", views.decide, name="decide"),
    path("approvals/series/<int:pk>/", views.decide_series, name="decide_series"),
]
