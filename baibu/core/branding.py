"""Language configuration for white-label deployments.

Settings import these helpers, so they must not import Django models or
settings themselves.
"""

from django.conf.locale import LANG_INFO


class LanguageConfigError(ValueError):
    """Raised when the language settings cannot be turned into LANGUAGES."""


def parse_extra_languages(spec: str) -> dict[str, dict]:
    """Parse ``"code:English name:Local name; ..."`` into Django LANG_INFO entries.

    The local name is optional and defaults to the English name.
    """
    languages: dict[str, dict] = {}
    for raw_entry in (spec or "").split(";"):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split(":")]
        code = parts[0].lower()
        if not code or len(parts) < 2 or not parts[1]:
            msg = f"Extra language entry {entry!r} must look like 'code:English name[:Local name]'."
            raise LanguageConfigError(msg)
        name = parts[1]
        name_local = parts[2] if len(parts) > 2 and parts[2] else name
        languages[code] = {"bidi": False, "code": code, "name": name, "name_local": name_local}
    return languages


def register_extra_languages(spec: str) -> dict[str, dict]:
    """Teach Django about languages it does not ship so they can be activated."""
    languages = parse_extra_languages(spec)
    LANG_INFO.update(languages)
    return languages


def build_languages(codes: list[str], *, default: str) -> list[tuple[str, str]]:
    """Build the LANGUAGES setting from language codes.

    Each code must be known to Django, either built in or registered with
    ``register_extra_languages``. The default language must be one of them.
    """
    languages: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_code in codes:
        code = raw_code.strip().lower()
        if not code or code in seen:
            continue
        info = LANG_INFO.get(code)
        if info is None:
            msg = (
                f"Unknown language code {code!r}. Declare it in PLATFORM_EXTRA_LANGUAGES "
                "as 'code:English name:Local name'."
            )
            raise LanguageConfigError(msg)
        languages.append((code, info.get("name_local") or info["name"]))
        seen.add(code)
    if default not in seen:
        msg = f"PLATFORM_DEFAULT_LANGUAGE {default!r} must be listed in PLATFORM_LANGUAGES."
        raise LanguageConfigError(msg)
    return languages
