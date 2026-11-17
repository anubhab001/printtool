"""Shared data model for a print job, independent of OS backend."""

from __future__ import annotations

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
    """Backend-agnostic print settings. Each backend maps what it can and
    ignores/warns on anything it does not support."""

    printer: str | None = None  # None = system default printer
    copies: int = 1
    duplex: Duplex = Duplex.NONE
    paper_size: str | None = None  # e.g. "A4", "Letter"
    orientation: Orientation = Orientation.AUTO
    page_range: str | None = None  # e.g. "1-3,5"
    fit_to_page: bool = True
    collate: bool = True
    buffer_copy: bool = False  # copy to a temporary file before printing (protects removable media)
    delete_after_print: bool = False  # delete the original file once printing succeeds
    mirror_lr: bool = False  # mirror left-right before printing (PDF only)
    mirror_tb: bool = False  # mirror top-bottom before printing (PDF only)

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
        }
        data.update(overrides)
        return PrintSettings(**data)


class JobStatus(str, Enum):
    PENDING = "pending"
    PRINTING = "printing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PrintJob:
    """A single file to print with its own settings. Two queued jobs can
    share the same path (the same file queued twice, or duplicated), so
    job_id rather than path identifies a job in the queue."""

    path: Path
    settings: PrintSettings = field(default_factory=PrintSettings)
    status: JobStatus = JobStatus.PENDING
    message: str = ""
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # Set when this job is a zip member not yet extracted: (zip_path, chain).
    # `path` is a display-only stand-in until extraction actually happens,
    # right before this job is printed.
    pending_extract: tuple[Path, tuple[str, ...]] | None = None


@dataclass
class PrintResult:
    job: PrintJob
    success: bool
    message: str = ""
