"""Staff screens: review queues and processing errors."""

from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_http_methods

from baibu.chat import services as chat_services
from baibu.chat.models import ChatFlag
from baibu.chat.models import Run
from baibu.chat.models import ToolInvocation
from baibu.core import storage
from baibu.submissions import services as submission_services
from baibu.submissions.models import Submission

from .access import staff_required
from .forms import FlagDecisionForm
from .forms import SubmissionDecisionForm

QUEUE_STATUSES = (Submission.Status.NEEDS_REVIEW, Submission.Status.ISSUE)
ERROR_WINDOW_DAYS = 7


def _stored_text(key: str) -> str | None:
    payload = storage.read_json(key) if key else None
    return payload.get("text") if payload else None


@staff_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    since = timezone.now() - timedelta(days=ERROR_WINDOW_DAYS)
    context = {
        "needs_review": Submission.objects.filter(status=Submission.Status.NEEDS_REVIEW).count(),
        "issues": Submission.objects.filter(status=Submission.Status.ISSUE).count(),
        "open_flags": ChatFlag.objects.filter(status=ChatFlag.Status.OPEN).count(),
        "failed_runs": Run.objects.filter(status=Run.Status.FAILED, created_at__gte=since).count(),
        "failed_tools": ToolInvocation.objects.filter(
            status=ToolInvocation.Status.FAILED, created_at__gte=since
        ).count(),
        "window_days": ERROR_WINDOW_DAYS,
    }
    return render(request, "staff/dashboard.html", context)


# --- Submissions ------------------------------------------------------------


def _submission_queue(request):
    queryset = Submission.objects.filter(status__in=QUEUE_STATUSES).order_by("created_at")
    status = request.GET.get("status")
    if status in QUEUE_STATUSES:
        queryset = queryset.filter(status=status)
    return queryset


@staff_required
@cache_control(private=True, no_store=True)
@require_GET
def submission_queue(request: HttpRequest) -> HttpResponse:
    page = Paginator(_submission_queue(request), 50).get_page(request.GET.get("page"))
    return render(
        request,
        "staff/submission_queue.html",
        {"page": page, "status": request.GET.get("status", ""), "statuses": QUEUE_STATUSES},
    )


def _allowed_decisions(submission):
    return [d for d in ("verified", "rejected", "pending") if submission.can_transition_to(d)]


@staff_required
@cache_control(private=True, no_store=True)
@require_http_methods(["GET", "POST"])
def submission_detail(request: HttpRequest, pk) -> HttpResponse:
    submission = get_object_or_404(Submission.objects.select_related("user", "reviewed_by"), pk=pk)
    allowed = _allowed_decisions(submission)
    form = SubmissionDecisionForm(
        request.POST or None, allowed=allowed, initial={"staff_notes": submission.staff_notes}
    )
    if request.method == "POST" and form.is_valid():
        decision = form.cleaned_data["decision"]
        submission.staff_notes = form.cleaned_data["staff_notes"]
        submission.save(update_fields=["staff_notes", "updated_at"])
        if decision == "pending":
            done = submission_services.requeue(submission)
        else:
            done = submission_services.review(submission, decision, reviewer=request.user)
        if not done:
            messages.warning(request, _("This submission was already decided. Nothing was changed."))
            return redirect("staff:submission", pk=submission.pk)
        messages.success(request, _("Decision saved."))
        following = _submission_queue(request).exclude(pk=submission.pk).first()
        return redirect("staff:submission", pk=following.pk) if following else redirect("staff:submissions")
    return render(
        request,
        "staff/submission_detail.html",
        {
            "submission": submission,
            "form": form,
            "in_queue": submission.status in QUEUE_STATUSES,
            "raw_text": _stored_text(submission.raw_key),
            "clean_text": _stored_text(submission.clean_key),
        },
    )


# --- Reported chat replies --------------------------------------------------


@staff_required
@cache_control(private=True, no_store=True)
@require_GET
def flag_queue(request: HttpRequest) -> HttpResponse:
    flags = ChatFlag.objects.filter(status=ChatFlag.Status.OPEN).select_related("message", "conversation")
    page = Paginator(flags, 50).get_page(request.GET.get("page"))
    return render(request, "staff/flag_queue.html", {"page": page})


@staff_required
@cache_control(private=True, no_store=True)
@require_http_methods(["GET", "POST"])
def flag_detail(request: HttpRequest, pk) -> HttpResponse:
    flag = get_object_or_404(ChatFlag.objects.select_related("conversation", "message", "decided_by"), pk=pk)
    form = FlagDecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not chat_services.decide_flag(
            flag, form.cleaned_data["decision"], reviewer=request.user, note=form.cleaned_data["note"]
        ):
            messages.warning(request, _("This report was already decided. Nothing was changed."))
            return redirect("staff:flag", pk=flag.pk)
        messages.success(request, _("Decision saved."))
        following = ChatFlag.objects.filter(status=ChatFlag.Status.OPEN).first()
        return redirect("staff:flag", pk=following.pk) if following else redirect("staff:flags")
    transcript = flag.conversation.messages.all()
    return render(request, "staff/flag_detail.html", {"flag": flag, "form": form, "transcript": transcript})


# --- Errors -----------------------------------------------------------------


@staff_required
@cache_control(private=True, no_store=True)
@require_GET
def errors(request: HttpRequest) -> HttpResponse:
    since = timezone.now() - timedelta(days=ERROR_WINDOW_DAYS)
    return render(
        request,
        "staff/errors.html",
        {
            "issues": Submission.objects.filter(status=Submission.Status.ISSUE).order_by("-updated_at")[:100],
            "failed_runs": Run.objects.filter(status=Run.Status.FAILED, created_at__gte=since).order_by("-created_at")[
                :100
            ],
            "failed_tools": ToolInvocation.objects.filter(
                status=ToolInvocation.Status.FAILED, created_at__gte=since
            ).order_by("-created_at")[:100],
            "window_days": ERROR_WINDOW_DAYS,
        },
    )
