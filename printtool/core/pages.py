"""Best-effort page counts and rough consumption estimates for the
queue's status line. Only a PDF has a real page count available
without printing it; other formats just do not contribute one. The
ink/power/paper-area figures are rough, assumed-average-coverage
estimates, not a measurement of any real printer or page.
"""

from __future__ import annotations

import io
import tempfile

from . import scratch
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter, Transformation
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None
    PdfWriter = None
    Transformation = None

# cm^2, common sizes only; an unrecognised or unset paper_size falls back
# to A4 for the estimate, since that is what fit_to_page would scale to
# on most printers anyway.
_PAPER_AREA_CM2 = {
    "A4": 623.7,
    "A3": 1247.4,
    "LETTER": 603.2,
    "LEGAL": 791.6,
}

# Rough, average-coverage assumptions, not a measurement:
_ML_INK_PER_PAGE = 0.05
_KWH_PER_PAGE = 0.02


def count_pages(path: Path) -> int | None:
    if PdfReader is None or path.suffix.lower() != ".pdf" or not path.is_file():
        return None
    try:
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def count_pages_in_bytes(data: bytes) -> int | None:
    """A page count straight from a PDF's own bytes, so a zip member's
    page count is known before it is ever extracted to disk."""
    if PdfReader is None:
        return None
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return None


_PAPER_POINTS = {
    "A4": (595.0, 842.0),
    "A3": (842.0, 1190.0),
    "LETTER": (612.0, 792.0),
    "LEGAL": (612.0, 1008.0),
}


def _paper_points(paper_size: str | None) -> tuple[float, float]:
    return _PAPER_POINTS.get((paper_size or "A4").upper(), _PAPER_POINTS["A4"])


def build_blank_pdf(paper_size: str | None) -> Path:
    """A single, genuinely blank page at `paper_size`, for printer/paper
    checks that do not need any real content."""
    width, height = _paper_points(paper_size)
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    dest = scratch.folder("printtool-blank-") / "blank-page.pdf"
    with open(dest, "wb") as f:
        writer.write(f)
    return dest


def build_test_pdf(paper_size: str | None) -> Path:
    """A blank page with a border rectangle inset from each edge, as a
    quick visual check that a printer is not cropping or mis-scaling."""
    from pypdf.generic import DecodedStreamObject, NameObject

    width, height = _paper_points(paper_size)
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    margin = 18.0
    stream = DecodedStreamObject()
    stream.set_data(
        f"1 0 0 RG 2 w {margin} {margin} {width - 2 * margin} {height - 2 * margin} re S".encode()
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    dest = scratch.folder("printtool-test-") / "test-page.pdf"
    with open(dest, "wb") as f:
        writer.write(f)
    return dest


def mirror_pdf(path: Path, horizontal: bool, vertical: bool) -> Path | None:
    """A mirrored copy of `path` written to a fresh temp folder, or None
    when there is nothing to do (no mirroring requested, pypdf missing,
    or the file is not a PDF)."""
    if PdfReader is None or not (horizontal or vertical) or path.suffix.lower() != ".pdf":
        return None
    try:
        writer = PdfWriter(clone_from=str(path))
        for page in writer.pages:
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            transform = Transformation().scale(-1 if horizontal else 1, -1 if vertical else 1)
            transform = transform.translate(width if horizontal else 0, height if vertical else 0)
            page.add_transformation(transform)
        dest = scratch.folder("printtool-mirror-") / path.name
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    except Exception:
        return None


def grids_for(per_sheet: int) -> list[tuple[int, int]]:
    """(columns, rows) layouts for `per_sheet` pages, closest to square
    first: every exact fit, and for a prime count also the layouts of the
    next number with one cell left blank (7: 2 x 4, 4 x 2, 1 x 7, 7 x 1)."""
    if per_sheet <= 1:
        return [(1, 1)]

    def exact(n: int) -> set[tuple[int, int]]:
        return {(c, n // c) for c in range(1, n + 1) if n % c == 0}

    out = exact(per_sheet)
    if len(out) == 2 and per_sheet > 2:
        out |= {g for g in exact(per_sheet + 1) if min(g) > 1}
    return sorted(out, key=lambda g: (abs(g[0] - g[1]), g[1] < g[0]))


def cells(sheet_w: float, sheet_h: float, per_sheet: int, grid: tuple[int, int] | None = None,
          rows: tuple[int, ...] | None = None) -> list[list[tuple[float, float, float, float]]]:
    """The cells of a sheet, row by row from the top, each (x, y, w, h) with
    y measured from the bottom (as PDF does). A grid gives equal cells;
    `rows` gives each row its own count (2, 1: two above, one wide below)."""
    if rows:
        counts = [max(1, int(n)) for n in rows]
    else:
        cols, nrows = grid if grid and grid[0] * grid[1] >= per_sheet else grids_for(per_sheet)[0]
        counts = [cols] * nrows
    h = sheet_h / len(counts)
    out = []
    for r, n in enumerate(counts):
        w = sheet_w / n
        out.append([(c * w, sheet_h - (r + 1) * h, w, h) for c in range(n)])
    return out


def nup_pdf(path: Path, per_sheet: int, grid: tuple[int, int] | None = None, lines: tuple[str, ...] = (),
            rows: tuple[int, ...] | None = None) -> Path | None:
    """A copy of `path` with several pages scaled into cells on each sheet,
    reading left to right, top to bottom: `per_sheet` pages in a grid, or
    rows of their own (`rows`); optional lines between rows, between columns,
    or around each page. None when there is nothing to do (one per sheet,
    pypdf missing, or not a PDF)."""
    if rows:
        per_sheet = sum(rows)
    if PdfReader is None or per_sheet <= 1 or path.suffix.lower() != ".pdf":
        return None
    try:
        from pypdf import PageObject

        reader = PdfReader(str(path))
        sheet_w, sheet_h = float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)
        layout = cells(sheet_w, sheet_h, per_sheet, grid, rows)
        flat = [c for row in layout for c in row][:per_sheet]
        writer = PdfWriter()
        for start in range(0, len(reader.pages), per_sheet):
            sheet = PageObject.create_blank_page(width=sheet_w, height=sheet_h)
            for (cx, cy, cw, ch), page in zip(flat, reader.pages[start:start + per_sheet]):
                w, h = float(page.mediabox.width), float(page.mediabox.height)
                scale = min(cw / w, ch / h)
                tx = cx + (cw - w * scale) / 2
                ty = cy + (ch - h * scale) / 2
                sheet.merge_transformed_page(page, Transformation().scale(scale).translate(tx, ty))
            if lines:
                sheet.merge_page(_grid_lines(sheet_w, sheet_h, layout, lines))
            writer.add_page(sheet)
        dest = scratch.folder("printtool-nup-") / path.name
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    except Exception:
        return None


def _grid_lines(width: float, height: float, layout, lines) -> "PageObject":
    """A transparent page with thin grey lines for the cells of `layout`."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setStrokeGray(0.45)
    c.setLineWidth(0.6)
    for r, row in enumerate(layout):
        x0, y0, _w, h = row[0]
        if "rows" in lines and r > 0:
            c.line(0, y0 + h, width, y0 + h)
        if "columns" in lines:
            for (x, y, _cw, ch) in row[1:]:
                c.line(x, y, x, y + ch)
        if "frame" in lines:
            inset = 4
            for (x, y, cw, ch) in row:
                c.rect(x + inset, y + inset, cw - 2 * inset, ch - 2 * inset)
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def stamp_pdf(path: Path, date: bool = True, numbers: bool = False, signature: str | None = None) -> Path | None:
    """A copy of `path` with, on every page, any of: the date and time
    (bottom right), the page number (bottom centre) and a signature image
    (bottom left). Drawn with a reportlab overlay merged by pypdf. None
    when there is nothing to do or it cannot be done (not a PDF)."""
    if PdfReader is None or path.suffix.lower() != ".pdf" or not (date or numbers or signature):
        return None
    try:
        from datetime import datetime

        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        writer = PdfWriter(clone_from=str(path))
        stamp_text = datetime.now().strftime("%Y-%m-%d %H:%M")
        image = ImageReader(signature) if signature and Path(signature).exists() else None
        total = len(writer.pages)
        for n, page in enumerate(writer.pages, start=1):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(width, height))
            c.setFont("Helvetica", 8)
            if date:
                c.drawRightString(width - 18, 12, stamp_text)
            if numbers:
                c.drawCentredString(width / 2, 12, f"{n} / {total}")
            if image:
                iw, ih = image.getSize()
                h = 28
                c.drawImage(image, 18, 10, width=h * iw / ih, height=h, mask="auto")
            c.save()
            buf.seek(0)
            page.merge_page(PdfReader(buf).pages[0])
        dest = scratch.folder("printtool-stamp-") / path.name
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    except Exception:
        return None

def mostly_blank(path: Path, threshold_bytes: int = 200) -> bool | None:
    """A rough, content-stream-size heuristic for "this page has barely
    anything on it" -- not a real render/coverage analysis, just enough
    to flag an accidental blank page before it is printed. None means
    unknown (not a PDF, or it could not be read)."""
    if PdfReader is None or path.suffix.lower() != ".pdf":
        return None
    try:
        reader = PdfReader(str(path))
        if not reader.pages:
            return None

        def _blank(page) -> bool:
            contents = page.get_contents()
            return contents is None or len(contents.get_data()) < threshold_bytes

        return any(_blank(page) for page in reader.pages)
    except Exception:
        return None


def paper_area_cm2(paper_size: str | None, pages: int) -> float:
    area = _PAPER_AREA_CM2.get((paper_size or "A4").upper(), _PAPER_AREA_CM2["A4"])
    return area * pages


def rough_consumption(pages: int) -> tuple[float, float]:
    """(estimated mL of ink, estimated kWh), both rough averages."""
    return pages * _ML_INK_PER_PAGE, pages * _KWH_PER_PAGE


def sheets_needed(page_counts: list[int], per_sheet: int = 1, both_sides: bool = True, copies: int = 1, share: bool = False) -> int:
    """Sheets of paper for files of `page_counts` pages: pages per sheet
    first, then two sides per sheet; with `share`, a file may start on the
    back of the previous file's last sheet."""
    sides_per_sheet = 2 if both_sides else 1
    faces = [-(-n // max(per_sheet, 1)) for n in page_counts if n > 0]
    if share and both_sides:
        return -(-sum(faces) // sides_per_sheet) * copies
    return sum(-(-f // sides_per_sheet) for f in faces) * copies


def concat_pdfs(paths: list[Path]) -> Path | None:
    """One PDF with the pages of `paths` in order."""
    if PdfReader is None or not paths:
        return None
    try:
        writer = PdfWriter()
        for path in paths:
            for page in PdfReader(str(path)).pages:
                writer.add_page(page)
        dest = scratch.folder("printtool-join-") / "joined.pdf"
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    except Exception:
        return None


def interleave_pdfs(paths: list[Path]) -> Path | None:
    """One PDF taking page 1 of every file, then page 2 of every file that
    has one, and so on."""
    if PdfReader is None or not paths:
        return None
    try:
        readers = [PdfReader(str(p)) for p in paths]
        writer = PdfWriter()
        for i in range(max(len(r.pages) for r in readers)):
            for r in readers:
                if i < len(r.pages):
                    writer.add_page(r.pages[i])
        dest = scratch.folder("printtool-interleave-") / "interleaved.pdf"
        with open(dest, "wb") as f:
            writer.write(f)
        return dest
    except Exception:
        return None
