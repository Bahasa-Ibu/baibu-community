from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from baibu.localization import services
from baibu.localization.extraction import ExtractionError


class Command(BaseCommand):
    help = (
        "Extract the interface strings from the code (and the deployment's templates) and merge them "
        "into every language's translation draft, keeping existing translations."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Store the template even if it has not changed.")

    def handle(self, *args, force=False, **options):
        if not services.translatable_languages():
            self.stdout.write("Only the source language is enabled; nothing to translate.")
            return
        try:
            result = services.update_sources(force=force)
        except ExtractionError as exc:
            raise CommandError(str(exc)) from exc
        state = "updated" if result.created else "unchanged"
        merged = ", ".join(result.merged) or "none"
        self.stdout.write(f"Source strings {state} ({result.source.entry_count} messages). Drafts updated: {merged}.")
