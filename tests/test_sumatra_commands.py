from pathlib import Path

from printtool.core.models import Duplex, Orientation, PrintSettings
from printtool.core.sumatra import build_command, build_print_settings_tokens


def test_tokens_default_settings():
    tokens = build_print_settings_tokens(PrintSettings())
    assert tokens == ["simplex", "fit"]


def test_tokens_full_settings():
    settings = PrintSettings(
        copies=3,
        collate=False,
        duplex=Duplex.LONG_EDGE,
        paper_size="A4",
        orientation=Orientation.LANDSCAPE,
        page_range="1-3,5",
        fit_to_page=False,
    )
    tokens = build_print_settings_tokens(settings)
    assert tokens == [
        "3x",
        "nocollate",
        "duplexlong",
        "paper=A4",
        "landscape",
        "noscale",
        "1-3",
        "5",
    ]


def test_build_command_named_printer():
    cmd = build_command(Path("SumatraPDF.exe"), Path("doc.pdf"), PrintSettings(printer="Office Printer"))
    assert cmd == [
        "SumatraPDF.exe",
        "-silent",
        "-print-to",
        "Office Printer",
        "-print-settings",
        "simplex,fit",
        "doc.pdf",
    ]


def test_build_command_default_printer():
    cmd = build_command(Path("SumatraPDF.exe"), Path("doc.pdf"), PrintSettings())
    assert "-print-to-default" in cmd
    assert "-print-to" not in cmd
