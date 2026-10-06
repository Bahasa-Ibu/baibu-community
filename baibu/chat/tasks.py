from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist

from . import services


@shared_task(ignore_result=True)
def execute_run(run_id: str) -> str:
    run = services.execute(run_id)
    return run.status if run else "skipped"


@shared_task(ignore_result=True)
def tag_conversations() -> int:
    from .tagging import tag_due

    return tag_due()


@shared_task(ignore_result=True)
def sweep_runs() -> dict:
    return services.sweep_runs()


@shared_task(ignore_result=True)
def transcribe_audio(clip_id: str) -> str:
    try:
        clip = services.transcribe(clip_id)
    except ObjectDoesNotExist:
        # The conversation was deleted while the audio was being transcribed.
        return "deleted"
    return clip.status if clip else "skipped"


@shared_task(ignore_result=True)
def sweep_transcriptions() -> dict:
    return services.sweep_transcriptions()
