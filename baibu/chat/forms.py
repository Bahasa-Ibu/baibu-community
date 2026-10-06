from django import forms
from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.utils.translation import gettext_lazy as _


class MessageForm(forms.Form):
    content = forms.CharField(
        label=_("Message"),
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": _("Write a message")}),
    )
    idempotency_key = forms.CharField(widget=forms.HiddenInput, max_length=64)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content"].max_length = settings.CHAT_MAX_MESSAGE_CHARACTERS
        self.fields["content"].validators.append(MaxLengthValidator(settings.CHAT_MAX_MESSAGE_CHARACTERS))
        self.fields["content"].widget.attrs["maxlength"] = settings.CHAT_MAX_MESSAGE_CHARACTERS


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label=_("What is wrong with this reply?"), widget=forms.RadioSelect)
    note = forms.CharField(
        label=_("Anything else we should know? (optional)"),
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        from .models import ChatFlag

        super().__init__(*args, **kwargs)
        self.fields["reason"].choices = ChatFlag.Reason.choices
