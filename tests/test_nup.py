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


def test_sheet_count():
    from printtool.core.pages import sheets_needed

    assert sheets_needed([5], 1, True) == 3
    assert sheets_needed([5, 3], 1, True) == 5
    assert sheets_needed([5, 3], 1, True, share=True) == 4
    assert sheets_needed([7], 4, True) == 1
    assert sheets_needed([2], 1, False, copies=3) == 6


def test_pages_interleave(tmp_path):
    from printtool.core.pages import interleave_pdfs

    paths = []
    for name, n in (("a", 2), ("b", 1)):
        w = PdfWriter()
        for _ in range(n):
            w.add_blank_page(width=100 + len(paths), height=100)
        p = tmp_path / f"{name}.pdf"
        with p.open("wb") as fh:
            w.write(fh)
        paths.append(p)
    widths = [float(pg.mediabox.width) for pg in PdfReader(str(interleave_pdfs(paths))).pages]
    assert widths == [100, 101, 100]


def test_rows_of_their_own(tmp_path):
    from printtool.core.pages import cells

    src = tmp_path / "doc.pdf"
    w = PdfWriter()
    for _ in range(6):
        w.add_blank_page(width=595, height=842)
    with src.open("wb") as fh:
        w.write(fh)
    out = nup_pdf(src, 1, rows=(2, 1), lines=("rows", "columns", "frame"))
    assert len(PdfReader(str(out)).pages) == 2  # three pages a sheet
    layout = cells(600, 800, 3, rows=(2, 1))
    assert [len(r) for r in layout] == [2, 1]
    assert layout[1][0] == (0, 0, 600, 400)  # the lower row one wide cell
