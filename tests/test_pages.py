from pathlib import Path

from printtool.core.pages import count_pages, paper_area_cm2, rough_consumption


def _make_pdf(tmp_path, pages=1):
    from pypdf import PdfWriter

    path = tmp_path / "deck.pdf"
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def test_count_pages_pdf(tmp_path):
    path = _make_pdf(tmp_path, pages=3)
    assert count_pages(path) == 3


def test_count_pages_non_pdf(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("x")
    assert count_pages(path) is None


def test_count_pages_missing_file(tmp_path):
    assert count_pages(tmp_path / "nope.pdf") is None


def test_paper_area_known_size():
    assert paper_area_cm2("A4", 1) == 623.7
    assert paper_area_cm2("a4", 2) == 623.7 * 2


def test_paper_area_unknown_falls_back_to_a4():
    assert paper_area_cm2("Weird", 1) == paper_area_cm2("A4", 1)
    assert paper_area_cm2(None, 1) == paper_area_cm2("A4", 1)


def test_rough_consumption_scales_with_pages():
    ink1, power1 = rough_consumption(1)
    ink10, power10 = rough_consumption(10)
    assert ink10 == ink1 * 10
    assert power10 == power1 * 10
