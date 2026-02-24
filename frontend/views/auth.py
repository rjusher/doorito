"""Authentication views for the frontend app."""

from django.contrib import auth
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from frontend.forms.auth import FrontendLoginForm, FrontendRegisterForm


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Login page with session-based authentication."""
    if request.user.is_authenticated:
        return redirect("frontend:dashboard")

    if request.method == "POST":
        form = FrontendLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth.login(request, user)

            if not form.cleaned_data.get("remember_me"):
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(2592000)  # 30 days

            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url:
                return redirect(next_url)
            return redirect("frontend:dashboard")
    else:
        form = FrontendLoginForm(request)

    return render(
        request,
        "frontend/auth/login.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
        },
    )


@require_http_methods(["GET", "POST"])
def register_view(request):
    """Registration page — creates user and auto-logs in."""
    if request.user.is_authenticated:
        return redirect("frontend:dashboard")

    if request.method == "POST":
        form = FrontendRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth.login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url:
                return redirect(next_url)
            return redirect("frontend:dashboard")
    else:
        form = FrontendRegisterForm()

    return render(
        request,
        "frontend/auth/register.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
        },
    )


def logout_view(request):
    """Logout and redirect to login."""
    auth.logout(request)
    return redirect("frontend:login")
