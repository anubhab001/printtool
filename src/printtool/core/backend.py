"""Picks the right OS backend and exposes a single, uniform API that the
CLI and GUI both call. This is the only module that needs to know a new
backend exists.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from . import pages
from .models import PrintJob, PrintResult, PrintSettings


def _backend():
    if sys.platform.startswith("win"):
        from . import backend_windows as impl

        return impl
    from . import backend_cups as impl

    return impl


def list_printers() -> list[str]:
    return _backend().list_printers()


def default_printer() -> str | None:
    return _backend().default_printer()


def print_file(path: Path, settings: PrintSettings) -> PrintResult:
    path = Path(path)
    job = PrintJob(path=path, settings=settings)
    temp_dirs: list[str] = []
    try:
        print_path = path
        if settings.buffer_copy:
            # Copy first, so a removable drive pulled after this point does
            # not interrupt the print (the backend reads the copy, not the
            # original).
            temp_dir = tempfile.mkdtemp(prefix="printtool-")
            temp_dirs.append(temp_dir)
            print_path = Path(temp_dir) / path.name
            shutil.copy2(path, print_path)

        if settings.mirror_lr or settings.mirror_tb:
            mirrored = pages.mirror_pdf(print_path, settings.mirror_lr, settings.mirror_tb)
            if mirrored is not None:
                temp_dirs.append(str(mirrored.parent))
                print_path = mirrored

        success, message = _backend().print_file(print_path, settings)

        if success and settings.delete_after_print:
            try:
                path.unlink()
            except OSError as exc:
                success = False
                message = f"printed, but could not delete original: {exc}"
    except Exception as exc:  # noqa: BLE001 - surface any backend failure uniformly
        return PrintResult(job=job, success=False, message=str(exc))
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return PrintResult(job=job, success=success, message=message)


def print_jobs(jobs: list[PrintJob]) -> list[PrintResult]:
    """Print each job (which may each carry different settings) in order."""
    results = []
    for job in jobs:
        result = print_file(job.path, job.settings)
        results.append(result)
    return results
