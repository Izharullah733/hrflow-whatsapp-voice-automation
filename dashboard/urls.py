from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from dashboard_app import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.home, name="home"),
    path("registrations/", views.registrations, name="registrations"),
    path("registrations/new/", views.registration_new, name="registration_new"),
    path("registrations/<uuid:record_id>/edit/", views.registration_edit, name="registration_edit"),
    path("reports/", views.reports, name="reports"),
    path("team/", views.team, name="team"),
    path("team/new/", views.team_new, name="team_new"),
]
