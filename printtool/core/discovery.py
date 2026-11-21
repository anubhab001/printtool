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


def shortcut_target(path: Path) -> Path | None:
    """The file a shortcut points to: a symbolic link's target, a Windows
    .lnk's target (read from the file itself, no shell needed), a .url's
    file:// address; None when it points nowhere that exists."""
    try:
        if path.is_symlink():
            t = path.resolve()
            return t if t.exists() else None
        suffix = path.suffix.lower()
        if suffix == ".lnk":
            t = _lnk_target(path.read_bytes())
        elif suffix == ".url":
            t = None
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("url=file:"):
                    from urllib.parse import unquote, urlparse

                    u = urlparse(line[4:])
                    t = unquote(u.path.lstrip("/") if u.netloc == "" else "//" + u.netloc + u.path)
        else:
            return None
        if t:
            p = Path(t)
            return p if p.exists() else None
    except OSError:
        return None
    return None


def _lnk_target(data: bytes) -> str | None:
    """The local path in a Windows shell link (.lnk): its LinkInfo's local
    base path (and common suffix), as the format (MS-SHLLINK) lays it out."""
    import struct

    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return None
    flags = struct.unpack_from("<I", data, 20)[0]
    pos = 76
    if flags & 0x01:  # HasLinkTargetIDList
        pos += 2 + struct.unpack_from("<H", data, pos)[0]
    if not flags & 0x02:  # no LinkInfo
        return None
    info = pos
    size, header = struct.unpack_from("<II", data, info)[:2]
    info_flags = struct.unpack_from("<I", data, info + 8)[0]
    if not info_flags & 0x01:  # no local path (a network one)
        return None
    base_off = struct.unpack_from("<I", data, info + 16)[0]
    suffix_off = struct.unpack_from("<I", data, info + 24)[0]
    if header >= 0x24:  # Unicode forms
        ubase = struct.unpack_from("<I", data, info + 28)[0]
        usuf = struct.unpack_from("<I", data, info + 32)[0]

        def wstr(o):
            end = o
            while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
                end += 2
            return data[o:end].decode("utf-16-le", "replace")

        return wstr(info + ubase) + wstr(info + usuf)

    def cstr(o):
        end = data.index(b"\x00", o)
        return data[o:end].decode("mbcs" if hasattr(__import__("codecs"), "lookup") and _has_mbcs() else "latin-1", "replace")

    return cstr(info + base_off) + cstr(info + suffix_off)


def _has_mbcs() -> bool:
    import codecs

    try:
        codecs.lookup("mbcs")
        return True
    except LookupError:
        return False


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
