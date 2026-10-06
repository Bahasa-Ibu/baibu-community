from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from baibu.core import storage

from .models import AudioClip


@receiver(post_delete, sender=AudioClip)
def delete_audio_file(sender, instance: AudioClip, **kwargs) -> None:
    """Remove the recording once the deletion is committed (also when the
    message, conversation or account is deleted)."""
    key = instance.storage_key
    transaction.on_commit(lambda: storage.delete(key))
