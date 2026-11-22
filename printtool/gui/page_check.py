"""Pages worth a question before printing: Each page of a PDF is drawn small and measured. A page with almost no ink is blank (it can be skipped, as if it were not there); a scan with a gray veil or specks all over has noise (it can be printed as is, or with the near-white noise filtered out, text and pictures untouched); a page whose content fills only a small part of the sheet can be zoomed to fill it. Nothing changes unless asked; a changed file is a copy in a working folder."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QImage

DPI_LOOK = 50  # small: enough to measure a page, quick for a long file
DPI_CLEAN = 200  # a filtered scan is drawn again at this resolution
DARK = 200  # darker than this (0 to 255) counts as ink
VEIL = (200, 245)  # a light gray between these, all over a page, is a scan's ambient noise
CLEAN_LEVEL = 225  # in a filtered scan, every channel at or above this turns white


@dataclass
class PageFinding:
    page: int  # from 0
    kind: str  # "blank", "noise" or "small"
    box: QRectF | None = None  # "small": the content, in fractions of the page (x, y, width, height)


@dataclass
class Choice:
    skip: set[int] = field(default_factory=set)
    clean: set[int] = field(default_factory=set)
    zoom: dict[int, QRectF] = field(default_factory=dict)

    def any(self) -> bool:
        return bool(self.skip or self.clean or self.zoom)


def on_white(img: QImage) -> QImage:
    """A drawn page on white paper: Qt draws a page on a clear ground, which reads as black once made gray."""
    from PySide6.QtGui import QPainter

    out = QImage(img.size(), QImage.Format_RGB888)
    out.fill(Qt.white)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def _gray(img: QImage) -> tuple[bytes, int, int, int]:
    g = on_white(img).convertToFormat(QImage.Format_Grayscale8)
    return bytes(g.constBits()), g.width(), g.height(), g.bytesPerLine()


def measure(img: QImage, shrink: float = 1.0) -> tuple[str | None, QRectF | None]:
    """What a drawn page is: "blank", "noise", "small" (with its content's box) or None (an ordinary page). `shrink`: How much the page is made smaller to fit the paper (an A0 scan on A4: about 4), so content that fills a fair part of a huge page but would print small is small too."""
    data, w, h, stride = _gray(img)
    dark_map = bytes(1 if v < DARK else 0 for v in range(256))
    veil_map = bytes(1 if VEIL[0] <= v < VEIL[1] else 0 for v in range(256))
    dark = data.translate(dark_map)
    veil = data.translate(veil_map)
    total = w * h
    ink = sum(dark[y * stride:y * stride + w].count(1) for y in range(h)) / max(1, total)
    gray = sum(veil[y * stride:y * stride + w].count(1) for y in range(h)) / max(1, total)
    if ink < 0.0015 and gray < 0.05:
        return "blank", None
    rows = [y for y in range(h) if dark.find(b"\x01", y * stride, y * stride + w) >= 0]
    left = min((dark.find(b"\x01", y * stride, y * stride + w) - y * stride for y in rows), default=0)
    right = max((dark.rfind(b"\x01", y * stride, y * stride + w) - y * stride for y in rows), default=w - 1)
    # Noise: A veil of light gray over much of the page, or ink in nearly every row while there is little of it (specks all over).
    if gray > 0.18 or (rows and len(rows) > 0.9 * h and ink < 0.03):
        return "noise", None
    if rows:
        box = QRectF(left / w, rows[0] / h, (right - left + 1) / w, (rows[-1] - rows[0] + 1) / h)
        # As it would come out on the paper: The share of the sheet it fills, the page shrunk to fit.
        if shrink > 1.4:
            if box.width() * box.height() < 0.5 and max(box.width(), box.height()) < 0.8:
                return "small", box
        elif box.width() * box.height() < 0.2 and box.width() < 0.6 and box.height() < 0.6:
            return "small", box
    return None, None


def check(path: Path, paper: tuple[float, float] | None = None) -> list[PageFinding]:
    """Every page of a PDF that is blank, noisy or small; [] if none (or the file cannot be drawn). `paper`: The sheet printed on, in points (a page much larger than it, such as a scan taken at A0, is judged as it will print)."""
    if path.suffix.lower() != ".pdf":
        return []
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    if doc.load(str(path)) != QPdfDocument.Error.None_:
        return []
    found = []
    for k in range(doc.pageCount()):
        size = doc.pagePointSize(k)
        img = doc.render(k, QSize(max(1, int(size.width() * DPI_LOOK / 72)), max(1, int(size.height() * DPI_LOOK / 72))))
        if img.isNull():
            continue
        shrink = max(size.width() / paper[0], size.height() / paper[1]) if paper else 1.0
        kind, box = measure(img, shrink)
        if kind:
            found.append(PageFinding(k, kind, box))
    doc.close()
    return found


def pages_text(numbers: list[int]) -> str:
    """Page numbers as one reads them: 1, 3-5, 9."""
    out, run = [], []
    for n in sorted(numbers):
        if run and n == run[-1] + 1:
            run.append(n)
        else:
            if run:
                out.append(f"{run[0] + 1}" if len(run) == 1 else f"{run[0] + 1}-{run[-1] + 1}")
            run = [n]
    if run:
        out.append(f"{run[0] + 1}" if len(run) == 1 else f"{run[0] + 1}-{run[-1] + 1}")
    return ", ".join(out)


PRESETS = {"blank": ("on_blank_page", "skip"), "noise": ("on_noisy_scan", "filter"), "small": ("on_small_content", "zoom")}


def ask(parent, name: str, found: list[PageFinding], presets: dict | None = None) -> Choice | None:
    """One dialog per file: What was found, and what to do about each kind (Print preselected: nothing changes unless chosen); a kind with a preset in the settings (skip, filter, zoom or print) is not asked about. None if printing is called off."""
    presets = presets or {}
    decided = {kind for kind in PRESETS if presets.get(PRESETS[kind][0], "ask") != "ask"}
    if all(f.kind in decided for f in found):
        return _preset_choice(found, presets)
    from PySide6.QtWidgets import QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Pages to check: {name}")
    lay = QVBoxLayout(dlg)
    groups = {}
    texts = {
        "blank": ("Blank or nearly blank page (a page number alone)", ("Skip (as if not there)", "Print"), 1),
        "noise": ("Scan with noise (a gray veil or specks)", ("Print as is", "Filter the noise (text and pictures kept)"), 0),
        "small": ("Content in a small part of the page", ("Print as is", "Zoom to fill the sheet"), 0),
    }
    for kind, (title, options, default) in texts.items():
        numbers = [f.page for f in found if f.kind == kind and kind not in decided]
        if not numbers:
            continue
        lay.addWidget(QLabel(f"<b>{title}</b>: page {pages_text(numbers)}"))
        group = QButtonGroup(dlg)
        for k, option in enumerate(options):
            b = QRadioButton(option)
            b.setChecked(k == default)
            group.addButton(b, k)
            lay.addWidget(b)
        groups[kind] = group
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText("Print")
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    if not dlg.exec():
        return None
    choice = _preset_choice([f for f in found if f.kind in decided], presets)
    for f in found:
        if f.kind in decided:
            continue
        picked = groups[f.kind].checkedId() if f.kind in groups else 1
        if f.kind == "blank" and picked == 0:
            choice.skip.add(f.page)
        elif f.kind == "noise" and picked == 1:
            choice.clean.add(f.page)
        elif f.kind == "small" and picked == 1 and f.box is not None:
            choice.zoom[f.page] = f.box
    return choice


def paper_tone(img: QImage) -> int:
    """Where a scan's paper starts: A little below its commonest gray (the veil the scanner left), never below 170, so text and pictures, darker, are kept."""
    data, w, h, stride = _gray(img)
    rows = b"".join(data[y * stride:y * stride + w] for y in range(h))
    counts = [rows.count(bytes([v])) for v in range(150, 256)]
    mode = 150 + max(range(len(counts)), key=counts.__getitem__)
    return max(170, min(CLEAN_LEVEL, mode - 12))


def _preset_choice(found: list[PageFinding], presets: dict) -> Choice:
    """What the settings decide without asking: skip, filter or zoom; print leaves a page as it is."""
    choice = Choice()
    for f in found:
        key, act = PRESETS[f.kind]
        if presets.get(key) != act:
            continue
        if f.kind == "blank":
            choice.skip.add(f.page)
        elif f.kind == "noise":
            choice.clean.add(f.page)
        elif f.box is not None:
            choice.zoom[f.page] = f.box
    return choice


def _cleaned_page(doc, k: int) -> QImage:
    """A noisy scanned page drawn again, every channel at or above CLEAN_LEVEL turned white: The light gray veil and faint specks go, anything darker (text, lines, pictures) stays exactly as it was."""
    size = doc.pagePointSize(k)
    level = paper_tone(doc.render(k, QSize(max(1, int(size.width() * DPI_LOOK / 72)), max(1, int(size.height() * DPI_LOOK / 72)))))
    img = doc.render(k, QSize(int(size.width() * DPI_CLEAN / 72), int(size.height() * DPI_CLEAN / 72)))
    img = on_white(img)
    lift = bytes(255 if v >= level else v for v in range(256))
    data = bytes(img.constBits()).translate(lift)
    out = QImage(data, img.width(), img.height(), img.bytesPerLine(), QImage.Format_RGB888)
    return out.copy()


def apply(path: Path, choice: Choice, paper: tuple[float, float] | None = None) -> Path:
    """The file with the chosen changes, as a copy in a working folder: Skipped pages left out, noisy ones filtered, small ones zoomed to fill their sheet (the paper printed on, when given: an A0 scan's wanted part becomes an A4 page)."""
    from pypdf import PdfReader, PdfWriter, Transformation
    from pypdf._page import PageObject

    from ..core import scratch

    reader = PdfReader(str(path))
    folder = scratch.folder("printtool-checked-")
    cleaned = {}
    if choice.clean:
        cleaned = _write_cleaned(path, sorted(choice.clean), folder)
    writer = PdfWriter()
    for k, page in enumerate(reader.pages):
        if k in choice.skip:
            continue
        if k in cleaned:
            writer.add_page(cleaned[k])
            continue
        if k in choice.zoom:
            box = choice.zoom[k]
            w, h = float(page.mediabox.width), float(page.mediabox.height)
            x0, y0 = float(page.mediabox.left), float(page.mediabox.bottom)
            sw, sh = paper if paper else (w, h)
            # The content's box in points (the drawn page's y runs down, the PDF's up), with a small margin.
            margin = 0.02
            bx, bw = (box.x() - margin) * w, (box.width() + 2 * margin) * w
            by, bh = (1 - box.y() - box.height() - margin) * h, (box.height() + 2 * margin) * h
            if (bw > bh) != (sw > sh):  # a wide part on a tall sheet: the sheet turned to suit it
                sw, sh = sh, sw
            scale = min(sw / max(1.0, bw), sh / max(1.0, bh))
            sheet = PageObject.create_blank_page(width=sw, height=sh)
            dx = (sw - bw * scale) / 2
            dy = (sh - bh * scale) / 2
            sheet.merge_transformed_page(page, Transformation().translate(-x0 - bx, -y0 - by).scale(scale).translate(dx, dy))
            writer.add_page(sheet)
            continue
        writer.add_page(page)
    out = folder / path.name
    with open(out, "wb") as f:
        writer.write(f)
    return out


def _write_cleaned(path: Path, numbers: list[int], folder: Path) -> dict:
    """The filtered pages, drawn into a PDF of their own at their own size; returned as pages to put in place."""
    from pypdf import PdfReader
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    doc.load(str(path))
    tmp = folder / "cleaned-pages.pdf"
    writer = QPdfWriter(str(tmp))
    writer.setResolution(DPI_CLEAN)
    painter = None
    for i, k in enumerate(numbers):
        size = doc.pagePointSize(k)
        writer.setPageLayout(QPageLayout(QPageSize(size, QPageSize.Point), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
        if painter is None:
            painter = QPainter(writer)
        else:
            writer.newPage()
        img = _cleaned_page(doc, k)
        painter.drawImage(QRectF(0, 0, writer.width(), writer.height()), img)
    if painter is not None:
        painter.end()
    doc.close()
    pages = PdfReader(str(tmp)).pages
    return {k: pages[i] for i, k in enumerate(numbers)}
