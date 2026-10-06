from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from baibu.core.branding import build_languages

from . import text as text_rules


def language_choices() -> list[tuple[str, str]]:
    return build_languages(settings.SUBMISSION_LANGUAGES, default=settings.SUBMISSION_LANGUAGES[0])


class SubmissionForm(forms.Form):
    language_code = forms.ChoiceField(label=_("Language"))
    text = forms.CharField(
        label=_("Your writing"),
        widget=forms.Textarea(attrs={"rows": 12}),
        help_text=_("A story, a conversation, a recipe, a song: anything you wrote yourself in this language."),
    )
    confirm = forms.BooleanField(
        label=_("I wrote this or have permission to share it, and I have left out other people's personal details."),
        error_messages={"required": _("Please confirm before submitting.")},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = language_choices()
        self.fields["language_code"].choices = choices
        if len(choices) == 1:
            self.fields["language_code"].initial = choices[0][0]
            self.fields["language_code"].widget = forms.HiddenInput()
        self.fields["text"].max_length = settings.SUBMISSION_MAX_CHARACTERS
        self.fields["text"].widget.attrs["maxlength"] = settings.SUBMISSION_MAX_CHARACTERS

    def clean_text(self) -> str:
        value = text_rules.normalise(self.cleaned_data["text"])
        if len(value) > settings.SUBMISSION_MAX_CHARACTERS:
            raise forms.ValidationError(
                _("Please keep it under %(limit)d characters."), params={"limit": settings.SUBMISSION_MAX_CHARACTERS}
            )
        if text_rules.word_count(value) < settings.SUBMISSION_MIN_WORDS:
            raise forms.ValidationError(
                _("Please write at least %(limit)d words."), params={"limit": settings.SUBMISSION_MIN_WORDS}
            )
        return value
