"""Locate and drive the SumatraPDF portable binary, the Windows print engine.

SumatraPDF (GPLv3) is never bundled inside this repository or any wheel we
publish. We only invoke it as a separate subprocess at runtime -- the user
(or `scripts/fetch_sumatra.py`) fetches the official portable build once and
this module finds it. See README.md for the licensing rationale.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .models import Duplex, Orientation, PrintSettings

ENV_VAR = "PRINTTOOL_SUMATRA_PATH"
_BINARY_NAME = "SumatraPDF.exe"


def _data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "printtool"


def default_install_path() -> Path:
    """Where fetch_sumatra.py places the portable binary."""
    return _data_dir() / _BINARY_NAME


def locate_sumatra() -> Path | None:
    """Best-effort search for SumatraPDF.exe. Returns None if not found."""
    env_path = os.environ.get(ENV_VAR)
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    if default_install_path().is_file():
        return default_install_path()

    on_path = shutil.which("SumatraPDF") or shutil.which(_BINARY_NAME)
    if on_path:
        return Path(on_path)

    for candidate in (
        Path(os.environ.get("PROGRAMFILES", "")) / "SumatraPDF" / _BINARY_NAME,
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "SumatraPDF" / _BINARY_NAME,
        _data_dir() / "SumatraPDF" / _BINARY_NAME,
    ):
        if candidate.is_file():
            return candidate

    return None


def build_print_settings_tokens(settings: PrintSettings) -> list[str]:
    """Translate our backend-agnostic settings into SumatraPDF's
    `-print-settings` comma-list tokens."""
    tokens: list[str] = []

    if settings.copies > 1:
        tokens.append(f"{settings.copies}x")
        tokens.append("collate" if settings.collate else "nocollate")

    duplex_token = {
        Duplex.NONE: "simplex",
        Duplex.LONG_EDGE: "duplexlong",
        Duplex.SHORT_EDGE: "duplexshort",
    }[settings.duplex]
    tokens.append(duplex_token)

    if settings.paper_size:
        tokens.append(f"paper={settings.paper_size}")

    if settings.orientation == Orientation.PORTRAIT:
        tokens.append("portrait")
    elif settings.orientation == Orientation.LANDSCAPE:
        tokens.append("landscape")

    tokens.append("fit" if settings.fit_to_page else "noscale")

    if settings.page_range:
        tokens.extend(part.strip() for part in settings.page_range.split(",") if part.strip())

    return tokens


def build_command(sumatra_path: Path, path: Path, settings: PrintSettings) -> list[str]:
    cmd = [str(sumatra_path), "-silent"]
    if settings.printer:
        cmd += ["-print-to", settings.printer]
    else:
        cmd += ["-print-to-default"]
    cmd += ["-print-settings", ",".join(build_print_settings_tokens(settings))]
    cmd += [str(path)]
    return cmd


def print_file(sumatra_path: Path, path: Path, settings: PrintSettings) -> tuple[bool, str]:
    cmd = build_command(sumatra_path, path, settings)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        return False, detail
    return True, "printed"


def list_printers() -> list[str]:
    """Enumerate Windows printers without a hard pywin32 dependency, falling
    back to pywin32 for the default-printer lookup when available."""
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Printer | Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        names = [line.strip() for line in out.stdout.splitlines() if line.strip()]
        if names:
            return names
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return []


def default_printer() -> str | None:
    try:
        import win32print  # type: ignore

        return win32print.GetDefaultPrinter()
    except Exception:
        return None
