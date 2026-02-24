"""
Frontend view decorators for authentication and store context.
"""

from functools import wraps

from django.shortcuts import redirect


def frontend_login_required(view_func):
    """
    Redirect unauthenticated users to /app/login/.

    Unlike Django's @login_required which redirects to /accounts/login/,
    this decorator uses the frontend login URL.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from urllib.parse import urlencode

            login_url = "/app/login/"
            params = urlencode({"next": request.get_full_path()})
            return redirect(f"{login_url}?{params}")
        return view_func(request, *args, **kwargs)

    return wrapper
