from pathlib import Path

from printtool.core import discovery


def test_lnk_target_read_from_file():
    data = (Path(__file__).parent / "data" / "report.lnk").read_bytes()
    assert discovery._lnk_target(data).lower() == r"c:\demo\documents\report.pdf"


def test_not_a_shortcut():
    assert discovery._lnk_target(b"not a link") is None
