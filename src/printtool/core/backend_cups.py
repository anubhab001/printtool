"""CUPS (`lp`/`lpstat`) backend -- used on Linux and macOS, which are both
CUPS under the hood. This gives us direct, silent printing of PDFs with no
viewer window, the same guarantee SumatraPDF provides on Windows.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .models import Duplex, Orientation, PrintSettings


def build_command(path: Path, settings: PrintSettings) -> list[str]:
    cmd = ["lp"]

    if settings.printer:
        cmd += ["-d", settings.printer]

    if settings.copies > 1:
        cmd += ["-n", str(settings.copies)]

    duplex_option = {
        Duplex.NONE: "one-sided",
        Duplex.LONG_EDGE: "two-sided-long-edge",
        Duplex.SHORT_EDGE: "two-sided-short-edge",
    }[settings.duplex]
    cmd += ["-o", f"sides={duplex_option}"]

    if settings.paper_size:
        cmd += ["-o", f"media={settings.paper_size}"]

    if settings.orientation == Orientation.LANDSCAPE:
        cmd += ["-o", "landscape"]

    if settings.page_range:
        cmd += ["-o", f"page-ranges={settings.page_range}"]

    cmd += ["-o", "fit-to-page" if settings.fit_to_page else "natural-scaling=100"]
    cmd += ["-o", f"Collate={'True' if settings.collate else 'False'}"]

    cmd += [str(path)]
    return cmd


def print_file(path: Path, settings: PrintSettings) -> tuple[bool, str]:
    cmd = build_command(path, settings)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        return False, detail
    return True, proc.stdout.strip() or "printed"


_PRINTER_LINE = re.compile(r"^printer\s+(\S+)", re.IGNORECASE)


def list_printers() -> list[str]:
    try:
        proc = subprocess.run(["lpstat", "-p"], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    printers = []
    for line in proc.stdout.splitlines():
        match = _PRINTER_LINE.match(line.strip())
        if match:
            printers.append(match.group(1))
    return printers


def default_printer() -> str | None:
    try:
        proc = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    # "system default destination: <name>" or "no system default destination"
    line = proc.stdout.strip()
    if ":" not in line:
        return None
    name = line.split(":", 1)[1].strip()
    return name or None
