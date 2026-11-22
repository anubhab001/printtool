"""The pages asked about before printing: A blank page found and skipped, a scan's grey veil found and filtered (text kept), small content found and zoomed."""
import os
import random
import sys

import pytest

pytest.importorskip("PySide6.QtPdf")


def _pdf(path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    for k in range(30):
        c.drawString(60, h - 60 - k * 18, f"An ordinary page of text, line {k}, wide enough to fill the line.")
    c.showPage()
    c.showPage()  # blank
    c.setFillColorRGB(0.86, 0.86, 0.86)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    for k in range(20):
        c.drawString(60, h - 80 - k * 18, f"Scanned text under the noise, line {k}.")
    c.showPage()
    c.setFont("Helvetica", 7)
    for k in range(8):
        c.drawString(40, h - 50 - k * 9, f"Small receipt line {k}  12.50")
    c.showPage()
    c.save()


def test_found_and_fixed(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)
    from pypdf import PdfReader

    from printtool.gui import page_check

    src = tmp_path / "mixed.pdf"
    _pdf(src)
    found = page_check.check(src)
    kinds = {f.page: f.kind for f in found}
    assert kinds == {1: "blank", 2: "noise", 3: "small"}
    choice = page_check.Choice(skip={1}, clean={2}, zoom={3: next(f.box for f in found if f.kind == "small")})
    out = page_check.apply(src, choice)
    assert len(PdfReader(str(out)).pages) == 3
    # The filtered page has no veil left, and its text is still there.
    assert "noise" not in {f.kind for f in page_check.check(out)}
    assert page_check.pages_text([0, 2, 3, 4, 8]) == "1, 3-5, 9"


def test_a0_scan_zoomed_onto_a4(tmp_path):
    """A scan taken at A0 whose wanted part is a quarter of it: Small as it would print on A4, and zoomed, it becomes an A4 page."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication(sys.argv)
    from pypdf import PdfReader
    from reportlab.lib.pagesizes import A0, A4
    from reportlab.pdfgen import canvas

    from printtool.gui import page_check

    src = tmp_path / "a0.pdf"
    c = canvas.Canvas(str(src), pagesize=A0)
    w, h = A0
    c.setFont("Helvetica", 40)
    for k in range(30):
        c.drawString(150, h - 200 - k * 50, f"Line {k} of the part that matters, on a huge page")
    c.showPage()
    c.save()
    found = page_check.check(src, A4)
    assert [f.kind for f in found] == ["small"]
    out = page_check.apply(src, page_check.Choice(zoom={0: found[0].box}), A4)
    box = PdfReader(str(out)).pages[0].mediabox
    assert sorted((round(float(box.width)), round(float(box.height)))) == sorted((round(A4[0]), round(A4[1])))


def test_presets_decide_without_asking():
    from PySide6.QtCore import QRectF

    from printtool.gui import page_check

    found = [page_check.PageFinding(1, "blank"), page_check.PageFinding(2, "small", QRectF(0, 0, 0.1, 0.1))]
    c = page_check.ask(None, "x.pdf", found, {"on_blank_page": "skip", "on_small_content": "print"})
    assert c.skip == {1} and not c.zoom
