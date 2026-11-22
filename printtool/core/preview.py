"""Preview is not a PDF renderer of its own: It hands the file to the PDF viewer the OS already has, the cheapest way to look at a file before a batch goes to paper.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_in_default_viewer(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def reveal_in_file_manager(path: Path) -> None:
    """Open the OS file manager with the file selected, not just opened."""
    if sys.platform.startswith("win"):
        subprocess.run(["explorer", "/select,", str(path)], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
    else:
        # No portable "select this file" on Linux across file managers; opening the containing folder is the closest equivalent.
        subprocess.run(["xdg-open", str(path.parent)], check=False)
