from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from baibu.users.consent import consent_state
from baibu.users.consent import latest_consent
from baibu.users.consent import record_consent
from baibu.users.forms import ConsentForm

from . import services
from .forms import MessageForm
from .models import Conversation
from .models import Run


def chat_enabled(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not settings.CHAT_ENABLED:
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


def chat_consent_required(view):
    """Ask once how conversations may be used before the first chat."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if latest_consent(user=request.user, scope=settings.CHAT_CONSENT_SCOPE) is None:
            return redirect(f"{reverse('chat:consent')}?next={request.get_full_path()}")
        return view(request, *args, **kwargs)

    return wrapper


def _wants_fragment(request) -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def _own_conversation(request, pk) -> Conversation:
    return get_object_or_404(Conversation, pk=pk, user=request.user)


def _messages_context(conversation: Conversation) -> dict:
    runs = list(conversation.runs.select_related("reply"))
    active = next((run for run in runs if run.status in Run.ACTIVE_STATUSES), None)
    latest_by_message = {}
    for run in runs:
        latest_by_message[run.triggering_message_id] = run
    failed = {message_id: run for message_id, run in latest_by_message.items() if run.status == Run.Status.FAILED}
    items = []
    for message in conversation.messages.all():
        failed_run = failed.get(message.pk)
        items.append(
            {
                "message": message,
                "failed_run": failed_run,
                "can_retry": bool(failed_run) and failed_run.attempt < settings.CHAT_MAX_ATTEMPTS and not active,
            }
        )
    return {"conversation": conversation, "items": items, "pending": active is not None}


@login_required
@chat_enabled
@cache_control(private=True, no_store=True)
@require_http_methods(["GET", "POST"])
def consent_view(request: HttpRequest) -> HttpResponse:
    scope = settings.CHAT_CONSENT_SCOPE
    state = consent_state(user=request.user, scope=scope)
    form = ConsentForm(request.POST or None, initial={"tier": state.tier if state.latest_record else None})
    form.fields["tier"].label = _("How may your conversations be used?")
    if request.method == "POST" and form.is_valid():
        if state.latest_record is None or form.cleaned_data["tier"] != state.tier:
            record_consent(
                user=request.user,
                tier=form.cleaned_data["tier"],
                source="chat",
                scope=scope,
                metadata={
                    "locale": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE),
                    "consent_text_version": settings.CONSENT_TEXT_VERSION,
                },
            )
        messages.success(request, _("Your choice was saved."))
        next_url = request.GET.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("chat:home")
    return render(request, "chat/consent.html", {"form": form, "consent_state": state})


@login_required
@chat_enabled
@chat_consent_required
@cache_control(private=True, no_store=True)
@require_GET
def home(request: HttpRequest) -> HttpResponse:
    conversations = Conversation.objects.filter(user=request.user)[:50]
    form = MessageForm(initial={"idempotency_key": services.new_idempotency_key()})
    return render(request, "chat/home.html", {"conversations": conversations, "form": form})


@login_required
@chat_enabled
@chat_consent_required
@require_POST
def new_conversation(request: HttpRequest) -> HttpResponse:
    form = MessageForm(request.POST)
    if not form.is_valid():
        conversations = Conversation.objects.filter(user=request.user)[:50]
        return render(request, "chat/home.html", {"conversations": conversations, "form": form}, status=400)
    # A repeated first send must not start a second conversation.
    existing = Conversation.objects.filter(
        user=request.user, messages__idempotency_key=form.cleaned_data["idempotency_key"]
    ).first()
    if existing:
        return redirect("chat:conversation", pk=existing.pk)
    conversation = services.start_conversation(user=request.user, language_code=request.LANGUAGE_CODE)
    services.send_message(
        conversation=conversation,
        content=form.cleaned_data["content"],
        idempotency_key=form.cleaned_data["idempotency_key"],
    )
    return redirect("chat:conversation", pk=conversation.pk)


@login_required
@chat_enabled
@chat_consent_required
@cache_control(private=True, no_store=True)
@require_GET
def conversation_view(request: HttpRequest, pk) -> HttpResponse:
    conversation = _own_conversation(request, pk)
    form = MessageForm(initial={"idempotency_key": services.new_idempotency_key()})
    conversations = Conversation.objects.filter(user=request.user)[:50]
    return render(
        request,
        "chat/conversation.html",
        {**_messages_context(conversation), "form": form, "conversations": conversations},
    )


@login_required
@chat_enabled
@cache_control(private=True, no_store=True)
@require_GET
def messages_view(request: HttpRequest, pk) -> HttpResponse:
    return _fragment(request, _own_conversation(request, pk))


def _fragment(request, conversation, *, status=200, error="") -> HttpResponse:
    context = _messages_context(conversation)
    response = render(request, "chat/_messages.html", {**context, "error": error}, status=status)
    response["X-Chat-Pending"] = "1" if context["pending"] else "0"
    response["X-Chat-Next-Key"] = services.new_idempotency_key()
    return response


@login_required
@chat_enabled
@chat_consent_required
@require_POST
def send_view(request: HttpRequest, pk) -> HttpResponse:
    conversation = _own_conversation(request, pk)
    form = MessageForm(request.POST)
    error = ""
    if form.is_valid():
        try:
            services.send_message(
                conversation=conversation,
                content=form.cleaned_data["content"],
                idempotency_key=form.cleaned_data["idempotency_key"],
            )
        except services.ChatError as exc:
            error = str(exc)
    else:
        error = " ".join(str(e) for errors in form.errors.values() for e in errors)
    if _wants_fragment(request):
        return _fragment(request, conversation, status=400 if error else 200, error=error)
    if error:
        messages.error(request, error)
    return redirect("chat:conversation", pk=conversation.pk)


@login_required
@chat_enabled
@require_POST
def retry_view(request: HttpRequest, run_id) -> HttpResponse:
    run = get_object_or_404(Run, pk=run_id, conversation__user=request.user)
    error = ""
    try:
        services.retry_run(run)
    except services.ChatError as exc:
        error = str(exc)
    if _wants_fragment(request):
        return _fragment(request, run.conversation, status=400 if error else 200, error=error)
    if error:
        messages.error(request, error)
    return redirect("chat:conversation", pk=run.conversation_id)


@login_required
@chat_enabled
@require_POST
def delete_view(request: HttpRequest, pk) -> HttpResponse:
    _own_conversation(request, pk).delete()
    messages.success(request, _("The conversation was deleted."))
    return redirect("chat:home")
