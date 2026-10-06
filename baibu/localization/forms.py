from django import forms
from django.utils.translation import gettext_lazy as _

from . import catalogues

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class PluralFormsForm(forms.Form):
    plural_forms = forms.CharField(
        label=_("Plural forms"),
        max_length=500,
        help_text=_("The gettext Plural-Forms rule for this language, for example “nplurals=1; plural=0;”."),
    )

    def clean_plural_forms(self):
        value = self.cleaned_data["plural_forms"].strip()
        try:
            catalogues.parse_plural_forms(value)
        except catalogues.CatalogueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return value


class UploadForm(forms.Form):
    file = forms.FileField(
        label=_("PO file"),
        help_text=_("Translations for messages in the draft are taken; other messages are ignored."),
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(_("The file is too large."))
        data = upload.read()
        try:
            catalogues.parse(data)
        except (catalogues.CatalogueError, UnicodeDecodeError) as exc:
            raise forms.ValidationError(_("This is not a valid PO file.")) from exc
        return data
