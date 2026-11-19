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


def test_prime_count_gets_near_fitting_grids():
    from printtool.core.pages import grids_for

    assert (2, 4) in grids_for(7) and (4, 2) in grids_for(7)
    assert grids_for(4)[0] == (2, 2)


def test_four_has_square_and_strip_layouts():
    from printtool.core.pages import grids_for

    assert set(grids_for(4)) >= {(2, 2), (1, 4), (4, 1)}


def test_lines_are_drawn_on_the_sheet(tmp_path):
    src = tmp_path / "doc.pdf"
    w = PdfWriter()
    for _ in range(4):
        w.add_blank_page(width=595, height=842)
    with src.open("wb") as fh:
        w.write(fh)
    plain = nup_pdf(src, 4, (2, 2))
    lined = nup_pdf(src, 4, (2, 2), ("rows", "columns", "frame"))
    plain_ops = PdfReader(str(plain)).pages[0].get_contents().get_data()
    lined_ops = PdfReader(str(lined)).pages[0].get_contents().get_data()
    assert len(lined_ops) > len(plain_ops)


def test_page_numbers_and_date_are_stamped(tmp_path):
    from printtool.core.pages import stamp_pdf

    src = tmp_path / "doc.pdf"
    w = PdfWriter()
    for _ in range(2):
        w.add_blank_page(width=595, height=842)
    with src.open("wb") as fh:
        w.write(fh)
    out = stamp_pdf(src, date=True, numbers=True)
    text = PdfReader(str(out)).pages[1].extract_text()
    assert "2 / 2" in text
    assert stamp_pdf(src, date=False) is None
