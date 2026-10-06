from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from . import services
from .models import Notification


@login_required
@cache_control(private=True, no_store=True)
@require_GET
def inbox(request: HttpRequest) -> HttpResponse:
    page = Paginator(Notification.objects.filter(user=request.user), 30).get_page(request.GET.get("page"))
    return render(request, "notifications/inbox.html", {"page": page})


@login_required
@require_POST
def open_notification(request: HttpRequest, pk) -> HttpResponse:
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    services.mark_read(notification)
    link = notification.link
    if link and url_has_allowed_host_and_scheme(link, allowed_hosts={request.get_host()}):
        return redirect(link)
    return redirect("notifications:inbox")


@login_required
@require_POST
def mark_all_read(request: HttpRequest) -> HttpResponse:
    services.mark_all_read(request.user)
    return redirect("notifications:inbox")
