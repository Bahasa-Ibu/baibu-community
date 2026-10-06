from .services import unread_count


def notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"unread_notifications": unread_count(user)}
