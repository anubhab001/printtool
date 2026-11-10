"""Windows backend: drives the SumatraPDF portable binary (see sumatra.py)."""

from __future__ import annotations

from pathlib import Path

from . import sumatra
from .models import PrintSettings


class SumatraNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "SumatraPDF.exe was not found. Run `python scripts/fetch_sumatra.py` "
            f"to download the portable build to {sumatra.default_install_path()}, "
            f"or set the {sumatra.ENV_VAR} environment variable to its path."
        )


def print_file(path: Path, settings: PrintSettings) -> tuple[bool, str]:
    binary = sumatra.locate_sumatra()
    if binary is None:
        raise SumatraNotFoundError()
    return sumatra.print_file(binary, path, settings)


def list_printers() -> list[str]:
    return sumatra.list_printers()


def default_printer() -> str | None:
    return sumatra.default_printer()
