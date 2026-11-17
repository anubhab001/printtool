"""Find printable files under a path.

Which extensions count as printable is not hardcoded here: it comes
from settings.yaml (printable_extensions, plus advanced_extensions
when advanced mode is on), so adding a format is a one-line edit to
that file rather than a code change. A format listed there is handed
to the OS backend (SumatraPDF/CUPS) exactly as a PDF would be; whether
it actually prints correctly depends on that backend's own support
for it, since no conversion step is added here.
"""

from __future__ import annotations

from pathlib import Path


def is_supported(path: Path, extensions: set[str]) -> bool:
    return path.suffix.lower().lstrip(".") in {e.lower().lstrip(".") for e in extensions}


# A shortcut points at a file; it is not itself printable content, and
# printing one directly would either fail outright or silently print
# whatever the OS decides to do with a .lnk/.desktop file. This is a
# safety exclusion, not a format preference, so it stays fixed here
# rather than in settings.yaml.
_SHORTCUT_EXTENSIONS = {".lnk", ".desktop", ".url", ".webloc"}


def is_shortcut(path: Path) -> bool:
    return path.suffix.lower() in _SHORTCUT_EXTENSIONS or path.is_symlink()


def find_printable_files(
    folder: Path,
    extensions: set[str],
    recursive: bool = False,
) -> list[Path]:
    """Return sorted, printable files under `folder` whose extension is
    in `extensions` (without dots, case-insensitive)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")

    allowed = {e.lower().lstrip(".") for e in extensions}
    pattern = "**/*" if recursive else "*"
    files = [
        p
        for p in folder.glob(pattern)
        if p.is_file() and not is_shortcut(p) and p.suffix.lower().lstrip(".") in allowed
    ]
    return sorted(files, key=lambda p: str(p).lower())
