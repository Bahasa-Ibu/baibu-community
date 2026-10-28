"""Staff screens for looking at conversations: search, transcript, runs and events."""

import json

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from baibu.chat.models import Conversation

from .access import staff_required

PAGE_SIZE = 50


def conversation_browsing(view):
    """404 when a deployment has turned conversation browsing off."""

    def wrapper(request, *args, **kwargs):
        if not settings.STAFF_CONVERSATION_BROWSING:
            raise Http404
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def search_filter(query: str) -> Q | None:
    """Conversations whose messages contain the text, or whose owner's email contains it.

    Empty search means no filter. Matching is case-insensitive.
    """
    query = query.strip()
    if not query:
        return None
    return Q(messages__content__icontains=query) | Q(user__email__icontains=query) | Q(title__icontains=query)


@staff_required
@conversation_browsing
@cache_control(private=True, no_store=True)
@require_GET
def conversation_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    conversations = Conversation.objects.select_related("user").order_by("-last_activity_at", "-id")
    condition = search_filter(query)
    if condition is not None:
        # Matching through messages can repeat a conversation once per match.
        conversations = conversations.filter(pk__in=Conversation.objects.filter(condition).values("pk"))
    page = Paginator(conversations, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "staff/conversation_list.html", {"page": page, "q": query})


@staff_required
@conversation_browsing
@cache_control(private=True, no_store=True)
@require_GET
def conversation_detail(request: HttpRequest, pk) -> HttpResponse:
    conversation = get_object_or_404(Conversation.objects.select_related("user"), pk=pk)
    events = [
        {"event": event, "payload": json.dumps(event.payload, indent=2, sort_keys=True, ensure_ascii=False)}
        for event in conversation.events.select_related("message")
    ]
    return render(
        request,
        "staff/conversation_detail.html",
        {
            "conversation": conversation,
            "transcript": conversation.messages.all(),
            "runs": conversation.runs.select_related("triggering_message"),
            "events": events,
        },
    )
