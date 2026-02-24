"""URL configuration for Doorito."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    """Liveness probe — no I/O, always returns 200."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("app/", include("frontend.urls")),
]
