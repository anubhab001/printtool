"""Persisted user defaults (a YAML file), so day-to-day choices like "always buffer-copy before printing" do not need re-picking every run.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import Duplex, Orientation, PrintSettings

DEFAULTS: dict = {
    "printer": None,
    "paper_size": None,
    "buffer_copy": True,
    "eject_after_print": False,
    "share_sheets": False,
    "print_order": "files",  # files, copies, pages
    "delete_after_print": False,
    "fit_to_page": True,
    "collate": True,
    "duplex": Duplex.LONG_EDGE.value,
    "orientation": Orientation.AUTO.value,
    "auto_preview_before_print": False,
    "printable_extensions": ["pdf"],
    "advanced_extensions": ["txt", "log", "html"],
    "auto_scan_pwd": True,
    "warn_on_blank_pages": True,
    "on_blank_page": "ask",  # ask, skip or print
    "on_noisy_scan": "ask",  # ask, filter or print
    "on_small_content": "ask",  # ask, zoom or print
    "presets": {},  # named sets of print settings (Advanced > Presets)
    "interleave_copies": False,
    "blank_page_insertion": "none",  # one of: none, before, after, both
    "stamp_timestamp": False,
}

# One comment per key, written above it when the file is (re)generated, so a hand-editor sees what each option does and what values it accepts without having to come back here.
_COMMENTS: dict = {
    "printer": "Printer name, or null to use the system default printer.",
    "paper_size": 'e.g. "A4" or "Letter"; null uses the printer\'s own default.',
    "buffer_copy": "Print from a temporary copy instead of the original (protects against a USB drive pulled mid-job).",
    "delete_after_print": "Delete the original file once it has printed successfully.",
    "eject_after_print": "Safely remove the drive the files came from (e.g., a pen drive) once all have printed.",
    "share_sheets": "On both sides, start each file on the back of the previous file's last sheet when it has a free side.",
    "print_order": "files (one file after another), copies (one copy of each file in turn), pages (page 1 of every file, then page 2, ...).",
    "fit_to_page": "Scale the page to fit the paper size.",
    "collate": "Collate multi-copy jobs.",
    "duplex": f"One of: {', '.join(d.value for d in Duplex)}.",
    "orientation": f"One of: {', '.join(o.value for o in Orientation)}.",
    "auto_preview_before_print": "Open each file in the default viewer right before it prints.",
    "printable_extensions": "File extensions (no dots) always offered as printable, e.g. when scanning a folder or zip.",
    "advanced_extensions": "Extra extensions offered only with advanced options on. Printing one works only as well as the OS backend (SumatraPDF/CUPS) supports that format; nothing here is converted to PDF first.",
    "auto_scan_pwd": "Queue the current folder's printable files (zip contents included) automatically on startup.",
    "warn_on_blank_pages": "Check each page before printing: A blank page can be skipped, a scan with noise filtered, small content zoomed to fill the sheet (asked file by file).",
    "on_blank_page": "A blank or nearly blank page (a page number alone): ask, skip or print.",
    "on_noisy_scan": "A scan with a gray veil or specks: ask, filter (text and pictures kept) or print.",
    "on_small_content": "Content in a small part of the page (a scan taken at A0, a receipt in a corner): ask, zoom (to fill the paper) or print.",
    "presets": "Named sets of print settings, saved and applied from Advanced > Presets.",
    "interleave_copies": "Round-robin one copy of each queued file at a time instead of finishing one file's copies before starting the next.",
    "blank_page_insertion": "Print an extra blank page before/after/both around every queued file; one of none, before, after, both.",
    "stamp_timestamp": "Stamp the current date/time in the bottom-right corner of every printed PDF page (PDF files only).",
}


def _dump_commented(data: dict) -> str:
    lines = []
    for key in DEFAULTS:
        if key not in data:
            continue
        comment = _COMMENTS.get(key)
        if comment:
            lines.append(f"# {comment}")
        lines.append(yaml.safe_dump({key: data[key]}, sort_keys=False).strip())
    return "\n".join(lines) + "\n"


def settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "printtool" / "settings.yaml"


def ensure_settings_file(path: Path | None = None) -> Path:
    """Write the file with its defaults if it does not exist yet, so a fresh install still has a real file to open and hand-edit, not just in-memory defaults conjured on demand."""
    path = path or settings_path()
    if not path.is_file():
        save_defaults(dict(DEFAULTS), path)
    return path


def load_defaults(path: Path | None = None) -> dict:
    path = path or settings_path()
    if not path.is_file():
        return dict(DEFAULTS)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save_defaults(data: dict, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = load_defaults(path)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    path.write_text(_dump_commented(merged), encoding="utf-8")


def load_extensions(path: Path | None = None, *, advanced: bool = False) -> set[str]:
    data = load_defaults(path)
    extensions = set(data["printable_extensions"])
    if advanced:
        extensions |= set(data["advanced_extensions"])
    return {e.lower().lstrip(".") for e in extensions}


def load_auto_scan_pwd(path: Path | None = None) -> bool:
    return bool(load_defaults(path)["auto_scan_pwd"])


def load_auto_preview(path: Path | None = None) -> bool:
    return bool(load_defaults(path)["auto_preview_before_print"])


def save_auto_preview(value: bool, path: Path | None = None) -> None:
    save_defaults({"auto_preview_before_print": value}, path)


def load_warn_on_blank_pages(path: Path | None = None) -> bool:
    return bool(load_defaults(path)["warn_on_blank_pages"])


def save_warn_on_blank_pages(value: bool, path: Path | None = None) -> None:
    save_defaults({"warn_on_blank_pages": value}, path)


def load_interleave_copies(path: Path | None = None) -> bool:
    return bool(load_defaults(path)["interleave_copies"])


def save_interleave_copies(value: bool, path: Path | None = None) -> None:
    save_defaults({"interleave_copies": value}, path)


def load_blank_page_insertion(path: Path | None = None) -> str:
    return str(load_defaults(path)["blank_page_insertion"])


def save_blank_page_insertion(value: str, path: Path | None = None) -> None:
    save_defaults({"blank_page_insertion": value}, path)


def default_print_settings(path: Path | None = None) -> PrintSettings:
    data = load_defaults(path)
    return PrintSettings(
        printer=data["printer"],
        paper_size=data["paper_size"],
        duplex=Duplex(data["duplex"]),
        orientation=Orientation(data["orientation"]),
        fit_to_page=data["fit_to_page"],
        collate=data["collate"],
        buffer_copy=data["buffer_copy"],
        delete_after_print=data["delete_after_print"],
    )
