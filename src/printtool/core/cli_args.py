"""Turn a PrintSettings back into the CLI flags that would reproduce it.
Used by the GUI's "schedule for later" action, which hands a deferred
print off to the OS scheduler as a `printtool print ...` invocation.
"""

from __future__ import annotations

from pathlib import Path

from .models import PrintSettings


def settings_to_args(path: Path, settings: PrintSettings) -> list[str]:
    args = ["print", str(path)]
    if settings.printer:
        args += ["--printer", settings.printer]
    args += ["--copies", str(settings.copies)]
    args += ["--duplex", settings.duplex.value]
    if settings.paper_size:
        args += ["--paper", settings.paper_size]
    args += ["--orientation", settings.orientation.value]
    if settings.page_range:
        args += ["--pages", settings.page_range]
    args.append("--fit" if settings.fit_to_page else "--no-fit")
    args.append("--collate" if settings.collate else "--no-collate")
    args.append("--buffer-copy" if settings.buffer_copy else "--no-buffer-copy")
    args.append("--delete-after-print" if settings.delete_after_print else "--no-delete-after-print")
    return args
