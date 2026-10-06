from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Submission
from .services import delete_files


@receiver(post_delete, sender=Submission)
def delete_submission_files(sender, instance: Submission, **kwargs) -> None:
    """Remove stored text once the deletion is committed (also on account deletion)."""
    transaction.on_commit(lambda: delete_files(instance))
