#!/usr/bin/env python3
"""Add printtool's GUI to the Start Menu (Windows) or application launcher
(Linux), so it can be opened without a terminal. Terminal invocation
(`printtool`, `printtool-gui`, or the standalone binaries) already works
without this script; this only adds the menu entry.

Usage:
    python scripts/install_shortcuts.py --target "C:\\path\\to\\printtool-gui-windows.exe"
    python scripts/install_shortcuts.py --target /path/to/printtool-gui-ubuntu
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def install_windows(target: Path, name: str) -> Path:
    import win32com.client  # type: ignore

    start_menu = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut_path = start_menu / f"{name}.lnk"

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target)
    shortcut.WorkingDirectory = str(target.parent)
    shortcut.Description = "Print PDFs directly, in batch, or from a folder"
    shortcut.Save()
    return shortcut_path


def install_linux(target: Path, name: str) -> Path:
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = apps_dir / "printtool.desktop"

    desktop_path.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={name}",
                "Comment=Print PDFs directly, in batch, or from a folder",
                f"Exec={target}",
                "Terminal=false",
                "Categories=Utility;Office;Printing;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    desktop_path.chmod(0o755)
    return desktop_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path, help="Path to the printtool GUI executable")
    parser.add_argument("--name", default="printtool", help="Menu entry name")
    args = parser.parse_args()

    if not args.target.is_file():
        print(f"No such file: {args.target}", file=sys.stderr)
        sys.exit(1)

    if sys.platform.startswith("win"):
        location = install_windows(args.target, args.name)
    else:
        location = install_linux(args.target, args.name)

    print(f"Menu entry installed: {location}")


if __name__ == "__main__":
    main()
