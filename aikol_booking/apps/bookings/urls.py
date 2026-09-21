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
    # The full booking register is an administrator workspace, not the
    # approver's pending queue.
    path("manage/bookings/", views.manage_bookings, name="manage"),
    path("manage/bookings/new/", views.admin_booking_start, name="admin_start"),
    path("manage/bookings/new/<int:pk>/", views.admin_booking_create, name="admin_create"),
    path(
        "manage/bookings/new/<int:pk>/weekly/",
        views.admin_series_create,
        name="admin_series_create",
    ),
    path("manage/bookings/user-search/", views.bookable_user_search, name="user_search"),
    path(
        "manage/bookings/<int:pk>/management/",
        views.vehicle_management_decision,
        name="vehicle_management",
    ),
    path("manage/academic-calendars/", views.academic_terms, name="academic_terms"),
    path("manage/academic-calendars/new/", views.academic_term_edit, name="academic_term_new"),
    path(
        "manage/academic-calendars/<int:pk>/",
        views.academic_term_edit,
        name="academic_term_edit",
    ),
    path(
        "manage/academic-calendars/<int:pk>/delete/",
        views.academic_term_delete,
        name="academic_term_delete",
    ),
    # Keys are held by the office, so these are administrator-only.
    path("manage/keys/", key_views.key_register, name="keys"),
    path("manage/keys/<int:pk>/issue/", key_views.key_issue, name="key_issue"),
    path("manage/keys/<int:pk>/return/", key_views.key_return, name="key_return"),
]
