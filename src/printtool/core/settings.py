"""Persisted user defaults (a YAML file), so day-to-day choices like
"always buffer-copy before printing" do not need re-picking every run.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import Duplex, Orientation, PrintSettings

DEFAULTS: dict = {
    "printer": None,
    "paper_size": None,
    "buffer_copy": False,
    "delete_after_print": False,
    "fit_to_page": True,
    "collate": True,
    "duplex": Duplex.NONE.value,
    "orientation": Orientation.AUTO.value,
    "auto_preview_before_print": False,
    "printable_extensions": ["pdf"],
    "advanced_extensions": ["txt", "log", "html"],
    "auto_scan_pwd": True,
}

# One comment per key, written above it when the file is (re)generated, so
# a hand-editor sees what each option does and what values it accepts
# without having to come back here.
_COMMENTS: dict = {
    "printer": "Printer name, or null to use the system default printer.",
    "paper_size": 'e.g. "A4" or "Letter"; null uses the printer\'s own default.',
    "buffer_copy": "Print from a temporary copy instead of the original (protects against a USB drive pulled mid-job).",
    "delete_after_print": "Delete the original file once it has printed successfully.",
    "fit_to_page": "Scale the page to fit the paper size.",
    "collate": "Collate multi-copy jobs.",
    "duplex": f"One of: {', '.join(d.value for d in Duplex)}.",
    "orientation": f"One of: {', '.join(o.value for o in Orientation)}.",
    "auto_preview_before_print": "Open each file in the default viewer right before it prints.",
    "printable_extensions": "File extensions (no dots) always offered as printable, e.g. when scanning a folder or zip.",
    "advanced_extensions": "Extra extensions offered only with advanced options on. Printing one works only as well as the OS backend (SumatraPDF/CUPS) supports that format; nothing here is converted to PDF first.",
    "auto_scan_pwd": "Queue the current folder's printable files (zip contents included) automatically on startup.",
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
    """Write the file with its defaults if it does not exist yet, so a
    fresh install still has a real file to open and hand-edit, not just
    in-memory defaults conjured on demand."""
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
