from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .report import COLUMNS

DEFAULT_RANGE_DAYS = 30


class RangeForm(forms.Form):
    """The days to show (inclusive) and the figure to chart."""

    start = forms.DateField(
        label=_("From"), required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    end = forms.DateField(
        label=_("To"), required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    chart = forms.ChoiceField(
        label=_("Chart"), required=False, choices=[(column.key, column.label) for column in COLUMNS]
    )

    @staticmethod
    def defaults() -> dict:
        end = timezone.localdate() - timedelta(days=1)
        return {"start": end - timedelta(days=DEFAULT_RANGE_DAYS - 1), "end": end, "chart": "active_users"}

    def clean(self):
        data = super().clean()
        defaults = self.defaults()
        end = data.get("end") or defaults["end"]
        start = data.get("start") or end - timedelta(days=DEFAULT_RANGE_DAYS - 1)
        if end > timezone.localdate():
            self.add_error("end", _("Choose a day that is not in the future."))
        if start > end:
            self.add_error("start", _("The first day must not be after the last day."))
        elif (end - start).days + 1 > settings.METRICS_MAX_RANGE_DAYS:
            self.add_error(
                None,
                _("Choose at most %(days)s days.") % {"days": settings.METRICS_MAX_RANGE_DAYS},
            )
        return {"start": start, "end": end, "chart": data.get("chart") or defaults["chart"]}

    def range(self) -> dict:
        """The chosen range if the form is valid, otherwise the default."""
        return self.cleaned_data if self.is_valid() else self.defaults()
