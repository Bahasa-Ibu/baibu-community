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


class VoiceForm(forms.Form):
    """A recorded voice message. The size and format are checked here; the
    audio itself is only read by the speech-to-text provider."""

    audio = forms.FileField(label=_("Voice message"))
    idempotency_key = forms.CharField(widget=forms.HiddenInput, max_length=64)

    def clean_audio(self):
        audio = self.cleaned_data["audio"]
        if audio.size > settings.CHAT_VOICE_MAX_BYTES:
            raise forms.ValidationError(_("The recording is too long."), code="too_large")
        content_type = (audio.content_type or "").split(";")[0].strip().lower()
        if content_type not in settings.CHAT_VOICE_CONTENT_TYPES:
            raise forms.ValidationError(_("This audio format is not supported."), code="content_type")
        audio.clean_content_type = content_type
        return audio
