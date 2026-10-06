# Import the Celery app when Django starts so that shared_task uses it.
from .celery import celery_app

__all__ = ("celery_app",)
