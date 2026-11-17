"""Schedule a one-off future print through the OS's own scheduler
(Task Scheduler on Windows, `at` on Linux/macOS), rather than an in-app
timer: the job then runs even if printtool itself is closed in the
meantime, exactly as if it had been run by hand at that time.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime


def _printtool_invocation() -> list[str]:
    """The command to re-run this same program, from inside a frozen
    PyInstaller binary or from a normal Python install alike."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "printtool.cli"]


def schedule_print(at: datetime, cli_args: list[str]) -> tuple[bool, str]:
    command = _printtool_invocation() + cli_args
    if sys.platform.startswith("win"):
        return _schedule_windows(at, command)
    return _schedule_unix(at, command)


def _schedule_windows(at: datetime, command: list[str]) -> tuple[bool, str]:
    task_name = f"printtool-{at.strftime('%Y%m%d%H%M%S')}"
    quoted = " ".join(f'"{part}"' if " " in part else part for part in command)
    # /ET is unavailable for ONCE tasks in schtasks's CLI, so the task is
    # left registered after it runs; it is harmless and visible in Task
    # Scheduler for manual cleanup.
    cmd = [
        "schtasks",
        "/create",
        "/tn",
        task_name,
        "/tr",
        quoted,
        "/sc",
        "once",
        "/st",
        at.strftime("%H:%M"),
        "/sd",
        at.strftime("%m/%d/%Y"),
        "/f",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, proc.stderr.strip() or proc.stdout.strip()
    return True, f"Scheduled as Task Scheduler task '{task_name}' for {at}"


def _schedule_unix(at: datetime, command: list[str]) -> tuple[bool, str]:
    if not shutil.which("at"):
        return False, (
            "The 'at' command is not installed/enabled "
            "(Debian/Ubuntu: `sudo apt install at && sudo systemctl enable --now atd`)."
        )
    quoted = " ".join(f"'{part}'" if " " in part else part for part in command)
    proc = subprocess.run(
        ["at", at.strftime("%H:%M %m/%d/%Y")],
        input=quoted + "\n",
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, proc.stderr.strip() or proc.stdout.strip()
    return True, f"Scheduled via 'at' for {at}: {proc.stderr.strip()}"
