"""Extracting the interface strings from the code into a gettext template.

This does what ``makemessages`` does for the ``django`` domain (templates are
converted with Django's own ``templatize`` and read by GNU ``xgettext`` with
the same keywords), but writes only to a temporary directory. The code
directory can stay read-only and nothing is written into the repository.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import polib
from django.conf import settings
from django.utils.translation import templatize

EXTENSIONS = {".py", ".html", ".txt"}
IGNORED_DIRS = {"tests", "migrations", "node_modules", "__pycache__", "static", "static_src"}
TEMPLATE_SUFFIX = ".py"

# The same keywords makemessages passes to xgettext for the django domain.
XGETTEXT_ARGS = [
    "--language=Python",
    "--from-code=UTF-8",
    "--add-comments=Translators",
    "--keyword=gettext_noop",
    "--keyword=gettext_lazy",
    "--keyword=ngettext_lazy:1,2",
    "--keyword=pgettext:1c,2",
    "--keyword=npgettext:1c,2,3",
    "--keyword=pgettext_lazy:1c,2",
    "--keyword=npgettext_lazy:1c,2,3",
]


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceRoot:
    """A directory to scan, and the name its files get in the template."""

    path: Path
    label: str


def default_roots() -> list[SourceRoot]:
    base = Path(settings.BASE_DIR)
    roots = [SourceRoot(Path(settings.APPS_DIR), "baibu"), SourceRoot(base / "config", "config")]
    deployment_templates = Path(settings.DEPLOYMENT_DIR) / "templates"
    if deployment_templates.is_dir():
        roots.append(SourceRoot(deployment_templates, "deployment/templates"))
    return roots


def _source_files(root: SourceRoot):
    for dirpath, dirnames, filenames in os.walk(root.path):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRS and not name.startswith("."))
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix in EXTENSIONS and not filename.startswith("."):
                yield path, f"{root.label}/{path.relative_to(root.path).as_posix()}"


def extract(roots: list[SourceRoot] | None = None) -> polib.POFile:
    """Return a template (.pot) with every translatable string under ``roots``."""
    xgettext = shutil.which("xgettext")
    if xgettext is None:
        msg = "xgettext was not found. Install GNU gettext (the Docker image includes it)."
        raise ExtractionError(msg)
    roots = default_roots() if roots is None else roots
    with tempfile.TemporaryDirectory(prefix="translation-sources-") as tmp:
        work = Path(tmp)
        names: list[str] = []
        for root in roots:
            for path, label in _source_files(root):
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                name = label
                if path.suffix != ".py":
                    content = templatize(content, origin=label)
                    name = label + TEMPLATE_SUFFIX
                target = work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                names.append(name)
        (work / "files.txt").write_text("\n".join(names), encoding="utf-8")
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            [xgettext, *XGETTEXT_ARGS, "--output=django.pot", "--files-from=files.txt"],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            msg = f"xgettext failed: {result.stderr.strip()}"
            raise ExtractionError(msg)
        pot_path = work / "django.pot"
        template = polib.pofile(str(pot_path)) if pot_path.exists() else polib.POFile()
    for entry in template:
        entry.occurrences = [
            (path.removesuffix(TEMPLATE_SUFFIX) if path.endswith((".html.py", ".txt.py")) else path, line)
            for path, line in entry.occurrences
        ]
    template.metadata = {
        "Project-Id-Version": "interface",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
    }
    return template
