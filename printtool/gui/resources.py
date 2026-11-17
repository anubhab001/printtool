"""Locate bundled image assets, whether running from source or from a
PyInstaller-frozen binary (which extracts data files under sys._MEIPASS).
"""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if hasattr(sys, "_MEIPASS"):
        return str(base / "printtool_gui_assets" / name)
    return str(Path(__file__).resolve().parent / "assets" / name)
