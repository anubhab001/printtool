"""Best-effort page counts and rough consumption estimates for the
queue's status line. Only a PDF has a real page count available
without printing it; other formats just do not contribute one. The
ink/power/paper-area figures are rough, assumed-average-coverage
estimates, not a measurement of any real printer or page.
"""

from __future__ import annotations

import io
import tempfile
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
    dest = Path(tempfile.mkdtemp(prefix="printtool-blank-")) / "blank-page.pdf"
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
    dest = Path(tempfile.mkdtemp(prefix="printtool-test-")) / "test-page.pdf"
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
        dest = Path(tempfile.mkdtemp(prefix="printtool-mirror-")) / path.name
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
