"""Odd or even pages, reverse order and booklet layout."""
from pypdf import PdfReader, PdfWriter

from printtool.core import pages


def _pdf(path, n):
    w = PdfWriter()
    for k in range(n):
        w.add_blank_page(width=100 + k, height=200)
    with open(path, "wb") as f:
        w.write(f)


def test_booklet_order():
    assert pages.booklet_order(8) == [(8, 1), (2, 7), (6, 3), (4, 5)]
    assert pages.booklet_order(5)[0] == (None, 1)


def test_arrange(tmp_path):
    src = tmp_path / "a.pdf"
    _pdf(src, 5)
    widths = lambda p: [round(float(x.mediabox.width)) for x in PdfReader(str(p)).pages]  # noqa: E731
    assert widths(pages.arrange_pdf(src, "odd")) == [100, 102, 104]
    assert widths(pages.arrange_pdf(src, "even", reverse=True)) == [103, 101]
    assert len(PdfReader(str(pages.arrange_pdf(src, booklet=True))).pages) == 4
    assert pages.arrange_pdf(src) is None
