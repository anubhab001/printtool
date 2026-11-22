"""Working folders for files made on the way to printing (stamped, N-up, mirrored, joined pages, test and blank pages): One per use, all removed when printtool closes. (Zip extraction keeps its own folder: a scheduled print may still need the file after printtool has closed.)"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

_made: list[Path] = []


def folder(prefix: str = "printtool-") -> Path:
    path = Path(tempfile.mkdtemp(prefix=prefix))
    _made.append(path)
    return path


@atexit.register
def _clean() -> None:
    for path in _made:
        shutil.rmtree(path, ignore_errors=True)
