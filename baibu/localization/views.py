"""Pages for translators: languages, the catalogue editor, publishing and history."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.utils.translation import to_locale
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import require_POST

from . import catalogues
from . import services
from .extraction import ExtractionError
from .forms import PluralFormsForm
from .forms import UploadForm
from .models import TranslationCatalogue
from .models import TranslationPublication
from .permissions import PERMISSION

logger = logging.getLogger(__name__)

STATES = ("untranslated", "fuzzy", "translated", "all")
PAGE_SIZE = 25
MAX_QUERY_LENGTH = 200


def translator_required(view):
    view = permission_required(PERMISSION, raise_exception=True)(view)
    view = login_required(view)
    return cache_control(private=True, no_store=True)(view)


def _language_name(language_code: str) -> str:
    names = dict(services.translatable_languages())
    if language_code not in names:
        raise Http404
    return names[language_code]


# Overview ------------------------------------------------------------------------


@translator_required
@require_GET
def index(request: HttpRequest) -> HttpResponse:
    existing = {catalogue.language_code: catalogue for catalogue in TranslationCatalogue.objects.all()}
    languages = []
    for code, name in services.translatable_languages():
        catalogue = existing.get(code)
        publication = services.latest_publication(code)
        row = {"code": code, "name": name, "publication": publication, "stats": None, "unpublished": False}
        if catalogue is not None:
            try:
                draft = services.read_draft(catalogue)
            except (FileNotFoundError, catalogues.CatalogueError):
                logger.exception("Could not read the %s draft", code)
            else:
                row["stats"] = catalogues.stats(draft)
                row["unpublished"] = services.has_unpublished_changes(draft, publication)
        languages.append(row)
    return render(
        request,
        "localization/index.html",
        {"languages": languages, "source": services.latest_source()},
    )


@translator_required
@require_POST
def update_sources(request: HttpRequest) -> HttpResponse:
    try:
        result = services.update_sources(user=request.user)
    except ExtractionError:
        logger.exception("Could not extract source strings")
        messages.error(request, _("The source strings could not be extracted. The error has been logged."))
        return redirect("localization:index")
    if result.created:
        messages.success(
            request,
            ngettext(
                "Source strings updated: %(count)d message.",
                "Source strings updated: %(count)d messages.",
                result.source.entry_count,
            )
            % {"count": result.source.entry_count},
        )
    else:
        messages.success(request, _("The source strings have not changed."))
    return redirect("localization:index")


# Editing -------------------------------------------------------------------------


def _edits_from_post(data, plural_count: int) -> list[services.Edit]:
    edits = []
    for key in data.getlist("key")[: PAGE_SIZE * 2]:
        values = [data.get(f"msgstr-{key}-{index}", "") for index in range(plural_count)]
        if f"msgstr-{key}-1" not in data:
            values = values[:1]
        edits.append(
            services.Edit(key=key, values=values, fuzzy=f"fuzzy-{key}" in data, seen=data.get(f"seen-{key}", ""))
        )
    return edits


def _matches(entry, query: str) -> bool:
    texts = [entry.msgid, entry.msgid_plural, entry.msgctxt, entry.msgstr, *entry.msgstr_plural.values()]
    return any(query in (text or "").casefold() for text in texts)


def _plural_labels(po) -> list[str]:
    try:
        examples = catalogues.plural_examples(catalogues.plural_forms(po))
    except catalogues.CatalogueError:
        examples = [[1], [2]]
    labels = []
    for index, numbers in enumerate(examples, start=1):
        if numbers:
            labels.append(
                _("Form %(number)d (n = %(examples)s…)")
                % {"number": index, "examples": ", ".join(str(n) for n in numbers)}
            )
        else:
            labels.append(_("Form %(number)d") % {"number": index})
    return labels


def _row(entry, *, plural_labels, submitted, errors) -> dict:
    key = catalogues.entry_key(entry)
    edit = submitted.get(key)
    if entry.msgid_plural:
        values = [entry.msgstr_plural[index] for index in sorted(entry.msgstr_plural)]
        labels = plural_labels
    else:
        values = [entry.msgstr]
        labels = [_("Translation")]
    if edit is not None:
        values = edit.values + [""] * (len(values) - len(edit.values))
    longest = max([len(entry.msgid), len(entry.msgid_plural or ""), *(len(value) for value in values)])
    fields = [
        {"name": f"msgstr-{key}-{index}", "label": labels[index] if index < len(labels) else "", "value": value}
        for index, value in enumerate(values)
    ]
    return {
        "key": key,
        "entry": entry,
        "state": catalogues.entry_state(entry),
        "seen": services.fingerprint(entry),
        "fields": fields,
        "rows": min(8, 1 + longest // 60),
        "fuzzy": edit.fuzzy if edit is not None else entry.fuzzy,
        "error": errors.get(key),
        "occurrences": [f"{path}:{line}" if line else path for path, line in entry.occurrences[:3]],
        "more_occurrences": max(0, len(entry.occurrences) - 3),
    }


@translator_required
@require_http_methods(["GET", "POST"])
def catalogue(request: HttpRequest, language_code: str) -> HttpResponse:
    language_name = _language_name(language_code)
    try:
        current = services.get_catalogue(language_code, user=request.user)
    except services.NoSourceError:
        messages.info(request, _("Extract the source strings first."))
        return redirect("localization:index")
    state = request.GET.get("state", "untranslated")
    state = state if state in STATES else "untranslated"
    query = request.GET.get("q", "").strip()[:MAX_QUERY_LENGTH]
    submitted: dict = {}
    errors: dict = {}
    if request.method == "POST":
        draft = services.read_draft(current)
        edits = _edits_from_post(request.POST, catalogues.plural_count(draft))
        result = services.save_entries(language_code, edits, user=request.user)
        if result.changed:
            messages.success(
                request,
                ngettext("%(count)d translation saved.", "%(count)d translations saved.", result.changed)
                % {"count": result.changed},
            )
        if result.conflicts:
            messages.warning(
                request,
                ngettext(
                    "%(count)d translation was changed by someone else while you were editing; "
                    "it was not overwritten. Check it below.",
                    "%(count)d translations were changed by someone else while you were editing; "
                    "they were not overwritten. Check them below.",
                    len(result.conflicts),
                )
                % {"count": len(result.conflicts)},
            )
        if not result.errors:
            return redirect(request.get_full_path())
        errors = result.errors
        submitted = {edit.key: edit for edit in edits if edit.key in errors}
        messages.error(request, _("Some translations were not saved. Correct them below."))
        current.refresh_from_db()

    draft = services.read_draft(current)
    entries = catalogues.active_entries(draft)
    counts = catalogues.stats(draft)
    if state != "all":
        entries = [entry for entry in entries if catalogues.entry_state(entry) == state]
    if query:
        folded = query.casefold()
        entries = [entry for entry in entries if _matches(entry, folded)]
    if errors:
        # Keep the entries being corrected on the page whatever the filter.
        shown = {catalogues.entry_key(entry) for entry in entries}
        entries += [
            entry
            for entry in catalogues.active_entries(draft)
            if catalogues.entry_key(entry) in errors and catalogues.entry_key(entry) not in shown
        ]
    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("page"))
    plural_labels = _plural_labels(draft)
    publication = services.latest_publication(language_code)
    return render(
        request,
        "localization/catalogue.html",
        {
            "language_code": language_code,
            "language_name": language_name,
            "catalogue": current,
            "counts": counts,
            "state": state,
            "states": [
                ("untranslated", _("Untranslated"), counts.untranslated),
                ("fuzzy", _("Needs review"), counts.fuzzy),
                ("translated", _("Translated"), counts.translated),
                ("all", _("All"), counts.total),
            ],
            "query": query,
            "page": page,
            "rows": [_row(entry, plural_labels=plural_labels, submitted=submitted, errors=errors) for entry in page],
            "publication": publication,
            "unpublished": services.has_unpublished_changes(draft, publication),
            "plural_form": PluralFormsForm(initial={"plural_forms": catalogues.plural_forms(draft)}),
            "upload_form": UploadForm(),
        },
    )


@translator_required
@require_POST
def plural_forms(request: HttpRequest, language_code: str) -> HttpResponse:
    _language_name(language_code)
    form = PluralFormsForm(request.POST)
    if form.is_valid():
        services.set_plural_forms(language_code, form.cleaned_data["plural_forms"], user=request.user)
        messages.success(request, _("Plural forms saved."))
    else:
        messages.error(request, " ".join(form.errors["plural_forms"]))
    return redirect("localization:catalogue", language_code=language_code)


@translator_required
@require_POST
def upload(request: HttpRequest, language_code: str) -> HttpResponse:
    _language_name(language_code)
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, " ".join(error for errors in form.errors.values() for error in errors))
        return redirect("localization:catalogue", language_code=language_code)
    result = services.import_catalogue(language_code, form.cleaned_data["file"], user=request.user)
    messages.success(
        request,
        ngettext(
            "%(count)d translation taken from the file.", "%(count)d translations taken from the file.", result.changed
        )
        % {"count": result.changed},
    )
    if result.errors:
        messages.warning(
            request,
            ngettext(
                "%(count)d translation was skipped because its placeholders do not match the original.",
                "%(count)d translations were skipped because their placeholders do not match the original.",
                len(result.errors),
            )
            % {"count": len(result.errors)},
        )
    return redirect("localization:catalogue", language_code=language_code)


@translator_required
@require_GET
def download(request: HttpRequest, language_code: str) -> HttpResponse:
    _language_name(language_code)
    current = get_object_or_404(TranslationCatalogue, language_code=language_code)
    response = HttpResponse(catalogues.dump(services.read_draft(current)), content_type="text/x-gettext-translation")
    response["Content-Disposition"] = f'attachment; filename="{to_locale(language_code)}.po"'
    return response


# Publishing ----------------------------------------------------------------------


@translator_required
@require_POST
def publish(request: HttpRequest, language_code: str) -> HttpResponse:
    _language_name(language_code)
    get_object_or_404(TranslationCatalogue, language_code=language_code)
    publication = services.publish(language_code, user=request.user)
    messages.success(
        request,
        _("Published version %(version)d. Every page uses it within a few seconds.")
        % {"version": publication.version},
    )
    return redirect("localization:catalogue", language_code=language_code)


@translator_required
@require_GET
def history(request: HttpRequest, language_code: str) -> HttpResponse:
    language_name = _language_name(language_code)
    publications = list(
        TranslationPublication.objects.filter(language_code=language_code)
        .select_related("published_by", "restored_from")
        .order_by("-version")
    )
    return render(
        request,
        "localization/history.html",
        {
            "language_code": language_code,
            "language_name": language_name,
            "publications": publications,
            "live": publications[0] if publications else None,
        },
    )


@translator_required
@require_POST
def restore(request: HttpRequest, language_code: str, pk) -> HttpResponse:
    _language_name(language_code)
    publication = get_object_or_404(TranslationPublication, pk=pk, language_code=language_code)
    restored = services.restore(publication, user=request.user)
    messages.success(
        request,
        _("Version %(old)d is live again, as version %(new)d. The draft was not changed.")
        % {"old": publication.version, "new": restored.version},
    )
    return redirect("localization:history", language_code=language_code)
