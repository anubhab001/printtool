"""Printing style: The pages of a PDF drawn again as color (unchanged), grayscale, washed out (lighter, less ink), high or low contrast, color negative, grayscale negative or sepia. Each page is drawn as a picture at the print resolution and written to a new PDF of the same page sizes; needs PySide6 (its PDF module)."""

from __future__ import annotations

from pathlib import Path

STYLES = (("Color", "color"), ("Grayscale", "gray"), ("Washed out", "washed"), ("High contrast", "high"), ("Low contrast", "low"),
          ("Color negative", "negative"), ("Grayscale negative", "gray_negative"), ("Sepia", "sepia"))
DPI = 200


def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


# One lookup table per style, for every channel alike (bytes.translate does the work).
_TABLES = {
    "washed": bytes(_clamp(255 - (255 - v) * 0.55) for v in range(256)),
    "high": bytes(_clamp((v - 128) * 1.45 + 128) for v in range(256)),
    "low": bytes(_clamp(70 + v * 185 / 255) for v in range(256)),  # the darks lifted, white paper kept white
    "negative": bytes(255 - v for v in range(256)),
}
# Sepia from a gray level: Warm browns in the middle tones; black stays black and white paper stays white (no ink spent on the paper).
_SEPIA = tuple(bytes(_clamp(255 * (v / 255) ** g) for v in range(256)) for g in (0.82, 1.0, 1.35))


def restyle_image(img, style: str):
    """One drawn page (a QImage) in `style`."""
    from PySide6.QtGui import QImage, QPainter

    flat = QImage(img.size(), QImage.Format_RGB888)
    flat.fill(0xFFFFFF)
    p = QPainter(flat)
    p.drawImage(0, 0, img)
    p.end()
    if style in ("gray", "gray_negative", "sepia"):
        gray = flat.convertToFormat(QImage.Format_Grayscale8)
        w, h, stride = gray.width(), gray.height(), gray.bytesPerLine()
        raw = bytes(gray.constBits())
        rows = b"".join(raw[y * stride:y * stride + w] for y in range(h))
        if style == "gray_negative":
            rows = rows.translate(_TABLES["negative"])
        if style != "sepia":
            return QImage(rows, w, h, w, QImage.Format_Grayscale8).copy()
        out = bytearray(len(rows) * 3)
        for k in range(3):
            out[k::3] = rows.translate(_SEPIA[k])
        return QImage(bytes(out), w, h, w * 3, QImage.Format_RGB888).copy()
    table = _TABLES.get(style)
    if table is None:
        return flat
    data = bytes(flat.constBits()).translate(table)
    return QImage(data, flat.width(), flat.height(), flat.bytesPerLine(), QImage.Format_RGB888).copy()


def restyle(path: Path, style: str, folder: Path) -> Path | None:
    """A copy of the PDF in `style`, in `folder`; None for color, a file that is not a PDF, or no PySide6."""
    if style in ("", "color") or Path(path).suffix.lower() != ".pdf":
        return None
    try:
        from PySide6.QtCore import QMarginsF, QRectF, QSize
        from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
        from PySide6.QtPdf import QPdfDocument
    except ImportError:
        return None
    doc = QPdfDocument()
    if doc.load(str(path)) != QPdfDocument.Error.None_:
        return None
    out = Path(folder) / Path(path).name
    writer = QPdfWriter(str(out))
    writer.setResolution(DPI)
    painter = None
    for k in range(doc.pageCount()):
        size = doc.pagePointSize(k)
        writer.setPageLayout(QPageLayout(QPageSize(size, QPageSize.Point), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
        if painter is None:
            painter = QPainter(writer)
        else:
            writer.newPage()
        img = doc.render(k, QSize(int(size.width() * DPI / 72), int(size.height() * DPI / 72)))
        painter.drawImage(QRectF(0, 0, writer.width(), writer.height()), restyle_image(img, style))
    if painter is not None:
        painter.end()
    doc.close()
    return out
