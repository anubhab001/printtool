"""Shared data model for a print job, independent of OS backend."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Duplex(str, Enum):
    NONE = "none"
    LONG_EDGE = "long_edge"
    SHORT_EDGE = "short_edge"


class Orientation(str, Enum):
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


@dataclass
class PrintSettings:
    """Backend-agnostic print settings. Each backend maps what it can and ignores/warns on anything it does not support."""

    printer: str | None = None  # None = system default printer
    copies: int = 1
    duplex: Duplex = Duplex.LONG_EDGE
    paper_size: str | None = None  # e.g. "A4", "Letter"
    orientation: Orientation = Orientation.AUTO
    page_range: str | None = None  # e.g. "1-3,5"
    fit_to_page: bool = True
    collate: bool = True
    buffer_copy: bool = False  # copy to a temporary file before printing (protects removable media)
    delete_after_print: bool = False  # delete the original file once printing succeeds
    mirror_lr: bool = False  # mirror left-right before printing (PDF only)
    mirror_tb: bool = False  # mirror top-bottom before printing (PDF only)
    which_pages: str = "all"  # all, odd or even
    reverse: bool = False  # last page first
    booklet: bool = False  # two pages per sheet side in folding order (print both sides, fold in the middle)
    style: str = "color"  # color, gray, washed, high, low, negative, gray_negative or sepia (PDF only; core/style.py)
    # Added to each page before printing (PDF only).
    stamp_date: bool = False
    page_numbers: bool = False
    signature: str | None = None  # path to a PNG or JPEG
    pages_per_sheet: int = 1  # PDF pages laid out on one side of a sheet
    pages_grid: tuple[int, int] | None = None  # (columns, rows); None picks the closest fit
    # Rows of their own, top to bottom (2, 1: two pages above, one wide below); when set, it is the layout and pages_per_sheet is its total.
    pages_rows: tuple[int, ...] | None = None
    # Lines drawn on a sheet of several pages: any of "rows" (between rows), "columns" (between columns), "frame" (around each page).
    pages_lines: tuple[str, ...] = ()

    def clone(self, **overrides) -> "PrintSettings":
        data = {
            "printer": self.printer,
            "copies": self.copies,
            "duplex": self.duplex,
            "paper_size": self.paper_size,
            "orientation": self.orientation,
            "page_range": self.page_range,
            "fit_to_page": self.fit_to_page,
            "collate": self.collate,
            "buffer_copy": self.buffer_copy,
            "delete_after_print": self.delete_after_print,
            "mirror_lr": self.mirror_lr,
            "mirror_tb": self.mirror_tb,
            "style": self.style,
            "which_pages": self.which_pages,
            "reverse": self.reverse,
            "booklet": self.booklet,
            "stamp_date": self.stamp_date,
            "page_numbers": self.page_numbers,
            "signature": self.signature,
            "pages_per_sheet": self.pages_per_sheet,
            "pages_grid": self.pages_grid,
            "pages_rows": self.pages_rows,
            "pages_lines": list(self.pages_lines),
        }
        data.update(overrides)
        return PrintSettings(**data)


class JobStatus(str, Enum):
    PENDING = "pending"
    PRINTING = "printing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


_SEQ = itertools.count()


@dataclass
class PrintJob:
    """A single file to print with its own settings. Two queued jobs can share the same path (the same file queued twice, or duplicated), so job_id rather than path identifies a job in the queue."""

    path: Path
    settings: PrintSettings = field(default_factory=PrintSettings)
    status: JobStatus = JobStatus.PENDING
    message: str = ""
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Order of inclusion into the queue, for the "Time included" sort.
    seq: int = field(default_factory=lambda: next(_SEQ))
    # Set when this job is a zip member not yet extracted: (zip_path, chain). `path` is a display-only stand-in until extraction actually happens, right before this job is printed.
    pending_extract: tuple[Path, tuple[str, ...]] | None = None


@dataclass
class PrintResult:
    job: PrintJob
    success: bool
    message: str = ""
