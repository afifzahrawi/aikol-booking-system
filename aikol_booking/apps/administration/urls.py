from django.urls import path

from . import views

app_name = "administration"

urlpatterns = [
    path("manage/", views.dashboard, name="dashboard"),
    path("manage/users/", views.user_list, name="users"),
    path("manage/users/<int:pk>/", views.user_edit, name="user_edit"),
    path("manage/settings/", views.settings_list, name="settings"),
    path("manage/site-content/", views.site_content, name="site_content"),
    path("manage/audit/", views.audit_log, name="audit"),
]
