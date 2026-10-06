from celery import shared_task

from .services import delete_old


@shared_task(ignore_result=True)
def delete_old_notifications() -> int:
    return delete_old()
