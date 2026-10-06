from datetime import date

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from baibu.metrics import rollups


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = f"Not a date (YYYY-MM-DD): {value}"
        raise CommandError(msg) from exc


class Command(BaseCommand):
    help = (
        "Compute the usage rollups for a range of days (default: yesterday), replacing stored values. "
        "Days are in the platform time zone."
    )

    def add_arguments(self, parser):
        parser.add_argument("--start", type=_date, help="First day, YYYY-MM-DD. Default: --end.")
        parser.add_argument("--end", type=_date, help="Last day, YYYY-MM-DD. Default: yesterday.")

    def handle(self, *args, start=None, end=None, **options):
        end = end or rollups.yesterday()
        start = start or end
        if start > end:
            msg = "--start must not be after --end."
            raise CommandError(msg)
        if end >= timezone.localdate():
            msg = "Only finished days can be computed; --end must be before today."
            raise CommandError(msg)
        days = rollups.store_range(start, end)
        self.stdout.write(f"Computed {days} day(s), {start} to {end}.")
