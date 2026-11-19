"""Safely removing the drive printed files came from (e.g., a pen drive)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def removable_drives(paths: list[Path]) -> list[str]:
    """Drive roots (e.g., "E:\\") among `paths` that are removable."""
    if sys.platform != "win32":
        return []
    import ctypes

    out = []
    for p in paths:
        drive = Path(p).anchor
        if drive and drive not in out and ctypes.windll.kernel32.GetDriveTypeW(drive) == 2:  # DRIVE_REMOVABLE
            out.append(drive)
    return out


def eject(drive: str) -> bool:
    """Asks Windows to remove the drive, as "Eject" in Explorer does."""
    if sys.platform != "win32":
        return False
    letter = drive.rstrip("\\")
    script = f'(New-Object -ComObject Shell.Application).Namespace(17).ParseName("{letter}").InvokeVerb("Eject")'
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
    return r.returncode == 0
