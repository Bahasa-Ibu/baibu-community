from celery import shared_task

from .models import Submission
from .services import run_cleaning


@shared_task(ignore_result=True)
def clean_submission(submission_id: str) -> str:
    submission = Submission.objects.filter(pk=submission_id).first()
    if submission is None:
        return "missing"
    return run_cleaning(submission).status
