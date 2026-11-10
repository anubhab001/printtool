#!/usr/bin/env python3
"""Download the official SumatraPDF portable build and unpack SumatraPDF.exe
into printtool's local data directory, so the Windows backend can find it.

We do this instead of bundling the binary in the repo/wheel because
SumatraPDF is GPLv3 -- shipping it ourselves would require this whole
project to ship under GPLv3-compatible terms. Downloading it on demand from
the official site, and only invoking it as a subprocess, keeps printtool's
own MIT license clean while still giving users one-command setup.

Usage:
    python scripts/fetch_sumatra.py [--version 3.6.1] [--dest PATH]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from printtool.core.sumatra import default_install_path  # noqa: E402

DEFAULT_VERSION = "3.6.1"
URL_TEMPLATE = "https://www.sumatrapdfreader.org/dl/rel/{version}/SumatraPDF-{version}-64.zip"


def fetch(version: str, dest: Path) -> Path:
    url = URL_TEMPLATE.format(version=version)
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {url} ...")
    zip_path = dest.parent / f"SumatraPDF-{version}-64.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request) as response, open(zip_path, "wb") as out:  # noqa: S310
        out.write(response.read())

    print(f"Extracting SumatraPDF.exe to {dest} ...")
    with zipfile.ZipFile(zip_path) as zf:
        # Portable builds ship as "SumatraPDF-<version>-64.exe", not a bare "SumatraPDF.exe".
        exe_names = [n for n in zf.namelist() if n.lower().startswith("sumatrapdf") and n.lower().endswith(".exe")]
        if not exe_names:
            raise RuntimeError("SumatraPDF.exe not found inside the downloaded archive")
        with zf.open(exe_names[0]) as src, open(dest, "wb") as out:
            out.write(src.read())

    zip_path.unlink(missing_ok=True)
    print(f"Done. SumatraPDF.exe installed at: {dest}")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION, help="SumatraPDF release version")
    parser.add_argument(
        "--dest", type=Path, default=None, help="Where to place SumatraPDF.exe (default: printtool data dir)"
    )
    args = parser.parse_args()

    if sys.platform != "win32":
        print("This script only applies on Windows; other platforms use CUPS instead.")
        sys.exit(1)

    dest = args.dest or default_install_path()
    fetch(args.version, dest)


if __name__ == "__main__":
    main()
