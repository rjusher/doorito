"""Dashboard view for the frontend app."""

from django.shortcuts import render

from frontend.decorators import frontend_login_required


@frontend_login_required
def dashboard_view(request):
    """Main dashboard page."""
    return render(request, "frontend/dashboard/index.html")
