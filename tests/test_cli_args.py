from pathlib import Path

from printtool.core.cli_args import settings_to_args
from printtool.core.models import Duplex, Orientation, PrintSettings


def test_settings_to_args_roundtrippable_shape():
    settings = PrintSettings(
        printer="Office",
        copies=2,
        duplex=Duplex.LONG_EDGE,
        paper_size="A4",
        orientation=Orientation.LANDSCAPE,
        page_range="1-3",
        fit_to_page=False,
        collate=False,
        buffer_copy=True,
        delete_after_print=True,
    )
    args = settings_to_args(Path("doc.pdf"), settings)

    assert args[:2] == ["print", "doc.pdf"]
    assert "--printer" in args and "Office" in args
    assert "--copies" in args and "2" in args
    assert "--duplex" in args and "long_edge" in args
    assert "--paper" in args and "A4" in args
    assert "--orientation" in args and "landscape" in args
    assert "--pages" in args and "1-3" in args
    assert "--no-fit" in args
    assert "--no-collate" in args
    assert "--buffer-copy" in args
    assert "--delete-after-print" in args
