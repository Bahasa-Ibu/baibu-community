from django import forms
from django.utils.translation import gettext_lazy as _

from baibu.chat.models import ChatFlag

SUBMISSION_DECISIONS = [
    ("verified", _("Accept")),
    ("rejected", _("Reject")),
    ("pending", _("Clean again")),
]


class SubmissionDecisionForm(forms.Form):
    decision = forms.ChoiceField(label=_("Decision"), choices=SUBMISSION_DECISIONS, widget=forms.RadioSelect)
    staff_notes = forms.CharField(
        label=_("Notes for staff (not shown to the contributor)"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, allowed=None, **kwargs):
        super().__init__(*args, **kwargs)
        if allowed is not None:
            self.fields["decision"].choices = [c for c in SUBMISSION_DECISIONS if c[0] in allowed]


class FlagDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        label=_("Decision"),
        choices=[(ChatFlag.Status.CONFIRMED, _("Problem confirmed")), (ChatFlag.Status.DISMISSED, _("No problem"))],
        widget=forms.RadioSelect,
    )
    note = forms.CharField(label=_("Notes for staff"), required=False, widget=forms.Textarea(attrs={"rows": 3}))
