from pathlib import Path

from printtool.core.backend_cups import build_command
from printtool.core.models import Duplex, Orientation, PrintSettings


def test_default_command():
    cmd = build_command(Path("doc.pdf"), PrintSettings())
    assert cmd == ["lp", "-o", "sides=one-sided", "-o", "fit-to-page", "-o", "Collate=True", "doc.pdf"]


def test_full_settings_command():
    settings = PrintSettings(
        printer="OfficePrinter",
        copies=2,
        duplex=Duplex.SHORT_EDGE,
        paper_size="A4",
        orientation=Orientation.LANDSCAPE,
        page_range="1-3",
        fit_to_page=False,
        collate=False,
    )
    cmd = build_command(Path("doc.pdf"), settings)
    assert cmd == [
        "lp",
        "-d", "OfficePrinter",
        "-n", "2",
        "-o", "sides=two-sided-short-edge",
        "-o", "media=A4",
        "-o", "landscape",
        "-o", "page-ranges=1-3",
        "-o", "natural-scaling=100",
        "-o", "Collate=False",
        "doc.pdf",
    ]
