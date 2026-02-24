"""
URL configuration for the frontend app.

All URLs are mounted under /app/ in boot/urls.py.
"""

from django.urls import path

from frontend.views import auth, dashboard

app_name = "frontend"

urlpatterns = [
    # Authentication
    path("login/", auth.login_view, name="login"),
    path("register/", auth.register_view, name="register"),
    path("logout/", auth.logout_view, name="logout"),
    # Dashboard
    path("", dashboard.dashboard_view, name="dashboard"),
]
