"""Printable files from outside the disk: A URL (file:// or web) and email
attachments dragged in. Everything lands in one buffer folder that is
removed when printtool closes.

- A link to a printable file (a PDF, or another printable type) is
  downloaded.
- A web page is searched for links to printable files; if it has none, the
  page itself is saved (it prints as HTML when advanced formats are on).
- An attachment dragged from a desktop mail program comes as a "virtual
  file" (a name and its bytes, no path); it is saved under its name.
"""

from __future__ import annotations

import atexit
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

_buffer: Path | None = None
_AGENT = {"User-Agent": "Mozilla/5.0 (printtool)"}


def buffer() -> Path:
    """The folder downloads and attachments go to; gone when printtool ends."""
    global _buffer
    if _buffer is None:
        _buffer = Path(tempfile.mkdtemp(prefix="printtool-buffer-"))
        atexit.register(shutil.rmtree, _buffer, True)
    return _buffer


def _free(path: Path) -> Path:
    stem, suffix, k = path.stem, path.suffix, 2
    while path.exists():
        path = path.with_name(f"{stem} ({k}){suffix}")
        k += 1
    return path


def _name_for(url: str, fallback: str = "download") -> str:
    name = urllib.parse.unquote(urllib.parse.urlparse(url).path).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c not in '<>:"/\\|?*' and ord(c) >= 32).strip(" .")
    return name or fallback


def download(url: str, folder: Path | None = None, name: str | None = None) -> Path:
    folder = folder or buffer()
    req = urllib.request.Request(url, headers=_AGENT)
    with urllib.request.urlopen(req, timeout=60) as r:
        if not name:
            disp = r.headers.get("Content-Disposition", "")
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disp)
            name = urllib.parse.unquote(m.group(1)) if m else _name_for(url)
            if "." not in name and "pdf" in r.headers.get("Content-Type", ""):
                name += ".pdf"
        dest = _free(folder / name)
        with open(dest, "wb") as f:
            while chunk := r.read(1 << 16):
                f.write(chunk)
    return dest


def look(url: str, extensions: set[str]) -> tuple[str, list[str]]:
    """What a URL is: ("file", [url]) for something printable, ("page",
    [links to printable files on it]) for a web page, ("local", [path])
    for file:// ."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        return "local", [urllib.request.url2pathname(parsed.path)]
    if Path(parsed.path).suffix.lower() in extensions:
        return "file", [url]
    req = urllib.request.Request(url, headers=_AGENT)
    with urllib.request.urlopen(req, timeout=30) as r:
        kind = r.headers.get("Content-Type", "")
        if "html" not in kind:
            return "file", [url]
        html = r.read(4_000_000).decode("utf-8", "replace")
    links = []
    for href in re.findall(r'href\s*=\s*["\']([^"\'#]+)', html, flags=re.IGNORECASE):
        full = urllib.parse.urljoin(url, href)
        if Path(urllib.parse.urlparse(full).path).suffix.lower() in extensions and full not in links:
            links.append(full)
    return "page", links


def save_page(url: str) -> Path:
    """The web page itself, as an HTML file in the buffer."""
    host = urllib.parse.urlparse(url).netloc or "page"
    return download(url, name=f"{host}.html")


def save_virtual(name: str, data: bytes) -> Path:
    """An attachment dragged from a mail program: Its name and bytes."""
    safe = "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "attachment"
    dest = _free(buffer() / safe)
    dest.write_bytes(data)
    return dest


def virtual_files(mime) -> list[Path]:
    """Attachments in a Windows drag ("FileGroupDescriptorW" names with
    "FileContents"), saved to the buffer. Qt hands over the first file's
    bytes; most mail programs drag one attachment at a time."""
    fmt = 'application/x-qt-windows-mime;value="FileGroupDescriptorW"'
    if fmt not in mime.formats():
        return []
    raw = bytes(mime.data(fmt))
    if len(raw) < 4:
        return []
    count = int.from_bytes(raw[:4], "little")
    names = []
    size = 592  # one FILEDESCRIPTORW
    for k in range(count):
        rec = raw[4 + k * size: 4 + (k + 1) * size]
        name = rec[72:].decode("utf-16-le", "ignore").split("\x00", 1)[0]
        names.append(name)
    data = bytes(mime.data('application/x-qt-windows-mime;value="FileContents"'))
    if not names or not data:
        return []
    return [save_virtual(names[0], data)]
