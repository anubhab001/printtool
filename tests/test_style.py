"""Printing style: A PDF drawn again in each style keeps its pages and their sizes; a negative turns white paper black."""
import os
import sys

import pytest

pytest.importorskip("PySide6.QtPdf")


def test_styles(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(sys.argv)
    from pypdf import PdfReader
    from reportlab.lib.pagesizes import A5, A4
    from reportlab.pdfgen import canvas

    from printtool.core import style

    src = tmp_path / "two.pdf"
    c = canvas.Canvas(str(src), pagesize=A4)
    c.setFillColorRGB(0.9, 0.2, 0.2)
    c.rect(100, 100, 200, 200, fill=1)
    c.showPage()
    c.setPageSize(A5)
    c.drawString(50, 50, "A smaller page")
    c.showPage()
    c.save()
    assert style.restyle(src, "color", tmp_path) is None
    for _label, value in style.STYLES[1:]:
        out_dir = tmp_path / value
        out_dir.mkdir()
        out = style.restyle(src, value, out_dir)
        pages = PdfReader(str(out)).pages
        assert len(pages) == 2
        assert round(float(pages[1].mediabox.width)) == round(A5[0])
    from PySide6.QtGui import QColor, QImage

    white = QImage(4, 4, QImage.Format_RGB888)
    white.fill(QColor("white"))
    assert style.restyle_image(white, "negative").pixelColor(1, 1).name() == "#000000"
    assert style.restyle_image(white, "sepia").pixelColor(1, 1).red() > 240
