import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from baibu.users.consent import consent_required
from baibu.users.models import ConsentRecord

from .forms import SubmissionForm
from .forms import language_choices
from .models import Submission
from .services import DuplicateSubmissionError
from .services import create_submission

logger = logging.getLogger(__name__)


def _consent_required(view):
    return consent_required(ConsentRecord.Tier.EVAL_ONLY, scope=settings.SUBMISSION_CONSENT_SCOPE)(view)


@login_required
@_consent_required
@cache_control(private=True, no_store=True)
@require_http_methods(["GET", "POST"])
def submission_create(request: HttpRequest) -> HttpResponse:
    form = SubmissionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_submission(
                user=request.user,
                raw_text=form.cleaned_data["text"],
                language_code=form.cleaned_data["language_code"],
            )
        except DuplicateSubmissionError:
            form.add_error("text", _("This text has already been submitted."))
        except Exception:
            logger.exception("Could not store a submission")
            form.add_error(None, _("We could not save your writing just now. Please try again later."))
        else:
            messages.success(request, _("Thank you. Your writing was received and will be checked shortly."))
            return redirect("submissions:list")
    return render(request, "submissions/create.html", {"form": form})


@login_required
@cache_control(private=True, no_store=True)
def submission_list(request: HttpRequest) -> HttpResponse:
    names = dict(language_choices())
    submissions = list(Submission.objects.filter(user=request.user))
    for submission in submissions:
        submission.language_name = names.get(submission.language_code, submission.language_code)
    return render(request, "submissions/list.html", {"submissions": submissions})


@login_required
@require_POST
def submission_delete(request: HttpRequest, pk) -> HttpResponse:
    submission = get_object_or_404(Submission, pk=pk, user=request.user)
    submission.delete()
    messages.success(request, _("Your submission was deleted."))
    return redirect("submissions:list")
