from django.urls import path

from . import key_views, views

app_name = "bookings"

urlpatterns = [
    path("bookings/", views.my_bookings, name="mine"),
    path("bookings/<int:pk>/", views.booking_detail, name="detail"),
    path("bookings/<int:pk>/cancel/", views.booking_cancel, name="cancel"),
    path("series/<int:pk>/cancel/", views.series_cancel, name="series_cancel"),
    path("resource/<int:pk>/availability/", views.availability, name="availability"),
    path("resource/<int:pk>/book/", views.booking_create, name="create"),
    # Read-only, for the form's live check. Never the decision.
    path("resource/<int:pk>/slot-check/", views.slot_check, name="slot_check"),
    path("resource/<int:pk>/book/weekly/", views.series_create, name="series_create"),
    # Deciding is the approver's authority, checked in the view.
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/<int:pk>/", views.decide, name="decide"),
    path("approvals/series/<int:pk>/", views.decide_series, name="decide_series"),
    # Keys are held by the office, so these are administrator-only.
    path("manage/keys/", key_views.key_register, name="keys"),
    path("manage/keys/<int:pk>/issue/", key_views.key_issue, name="key_issue"),
    path("manage/keys/<int:pk>/return/", key_views.key_return, name="key_return"),
]
