import io
import sys
import zipfile

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


def _pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)
    return buf.getvalue()


def test_zip_group_checkboxes(app, tmp_path, monkeypatch):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("b.pdf", _pdf_bytes())
    with zipfile.ZipFile(tmp_path / "outer.zip", "w") as z:
        z.writestr("a.pdf", _pdf_bytes())
        z.writestr("inner.zip", inner.getvalue())
    monkeypatch.chdir(tmp_path)

    from printtool.gui.app import MainWindow

    w = MainWindow()
    rows = {w.file_list.item(r).text().strip(): w.file_list.item(r) for r in range(w.file_list.count())}
    outer = rows[str(tmp_path / "outer.zip")]

    rows["b.pdf"].setCheckState(Qt.Unchecked)
    assert rows["inner.zip"].checkState() == Qt.Unchecked
    assert outer.checkState() == Qt.PartiallyChecked

    outer.setCheckState(Qt.Checked)
    assert rows["b.pdf"].checkState() == Qt.Checked
    assert rows["a.pdf"].checkState() == Qt.Checked
