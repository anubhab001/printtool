from pypdf import PdfReader, PdfWriter

from printtool.core.pages import nup_pdf


def test_four_pages_fit_on_one_sheet(tmp_path):
    src = tmp_path / "doc.pdf"
    w = PdfWriter()
    for _ in range(5):
        w.add_blank_page(width=595, height=842)
    with src.open("wb") as fh:
        w.write(fh)
    out = nup_pdf(src, 4)
    assert len(PdfReader(str(out)).pages) == 2
    assert nup_pdf(src, 1) is None
