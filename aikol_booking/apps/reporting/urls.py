from django.urls import path

from . import views

app_name = "reporting"

urlpatterns = [
    path("manage/reports/", views.reports, name="reports"),
]
