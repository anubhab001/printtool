from pathlib import Path

import pytest

from printtool.core.discovery import find_printable_files, is_shortcut, is_supported

PDF = {"pdf"}


def test_is_supported():
    assert is_supported(Path("report.pdf"), PDF)
    assert is_supported(Path("REPORT.PDF"), PDF)
    assert not is_supported(Path("slides.pptx"), PDF)


def test_is_supported_honours_arbitrary_extensions():
    assert is_supported(Path("notes.txt"), {"txt", "log"})
    assert not is_supported(Path("notes.txt"), {"log"})


def test_is_shortcut():
    assert is_shortcut(Path("link.lnk"))
    assert is_shortcut(Path("link.desktop"))
    assert not is_shortcut(Path("report.pdf"))


def test_find_printable_files_non_recursive(tmp_path):
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.pdf").write_text("x")

    found = find_printable_files(tmp_path, PDF, recursive=False)
    assert found == [tmp_path / "a.pdf"]


def test_find_printable_files_recursive(tmp_path):
    (tmp_path / "a.pdf").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.pdf").write_text("x")

    found = find_printable_files(tmp_path, PDF, recursive=True)
    assert found == sorted([tmp_path / "a.pdf", sub / "c.pdf"], key=lambda p: str(p).lower())


def test_find_printable_files_honours_custom_extensions(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.pdf").write_text("x")

    found = find_printable_files(tmp_path, {"txt"})
    assert found == [tmp_path / "a.txt"]


def test_find_printable_files_requires_directory(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(NotADirectoryError):
        find_printable_files(missing, PDF)
