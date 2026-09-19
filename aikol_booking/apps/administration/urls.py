from django.urls import path

from . import retention_views, views

app_name = "administration"

urlpatterns = [
    path("manage/", views.dashboard, name="dashboard"),
    path("manage/users/", views.user_list, name="users"),
    path("manage/users/<int:pk>/", views.user_edit, name="user_edit"),
    path("manage/users/<int:pk>/authenticator/reset/", views.user_mfa_reset, name="user_mfa_reset"),
    path("manage/settings/", views.settings_list, name="settings"),
    path("manage/site-content/", views.site_content, name="site_content"),
    path(
        "manage/site-content/announcements/new/",
        views.announcement_new,
        name="announcement_new",
    ),
    path(
        "manage/site-content/announcements/<int:pk>/",
        views.announcement_edit,
        name="announcement_edit",
    ),
    path("manage/audit/", views.audit_log, name="audit"),
    path("manage/retention/", retention_views.retention_screen, name="retention"),
]
