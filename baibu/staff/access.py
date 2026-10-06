from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def staff_required(view):
    """Signed-out users go to sign-in; signed-in users who are not staff get 403."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_active and request.user.is_staff):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
