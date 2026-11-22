"""Locate bundled image assets, whether running from source or from a PyInstaller-frozen binary (which extracts data files under sys._MEIPASS).
"""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> str:
    """The file beside this module (from source, and in a binary, which unpacks printtool/gui/assets to the same place); the older binary layout (printtool_gui_assets) if that is where it is."""
    here = Path(__file__).resolve().parent / "assets" / name
    if here.is_file() or not hasattr(sys, "_MEIPASS"):
        return str(here)
    return str(Path(sys._MEIPASS) / "printtool_gui_assets" / name)
