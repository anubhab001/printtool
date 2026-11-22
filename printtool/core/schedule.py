"""Schedule a one-off future print through the OS's own scheduler (Task Scheduler on Windows, `at` on Linux/macOS), rather than an in-app timer: the job then runs even if printtool itself is closed in the meantime, exactly as if it had been run by hand at that time.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path


def _printtool_invocation() -> list[str]:
    """The command to re-run printtool's CLI later, from inside a frozen PyInstaller binary or from a normal Python install alike. The GUI binary has no console and does not take CLI commands, so a schedule made from it runs the CLI binary beside it."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if "gui" in exe.name.lower():
            cli = exe.with_name(exe.name.lower().replace("gui", "cli"))
            if cli.exists():
                return [str(cli)]
        return [str(exe)]
    return [sys.executable, "-m", "printtool.cli"]


def absolute_files(cli_args: list[str]) -> list[str]:
    """Paths that exist made absolute: The scheduler runs the task from another folder (System32 on Windows)."""
    out = []
    for a in cli_args:
        p = Path(a)
        out.append(str(p.resolve()) if not a.startswith("-") and not p.is_absolute() and p.exists() else a)
    return out


def schedule_print(at: datetime, cli_args: list[str]) -> tuple[bool, str]:
    command = _printtool_invocation() + absolute_files(cli_args)
    if sys.platform.startswith("win"):
        return _schedule_windows(at, command)
    return _schedule_unix(at, command)


def _schedule_windows(at: datetime, command: list[str]) -> tuple[bool, str]:
    """Registered through PowerShell's Register-ScheduledTask with an ISO date, so the system's date format (dd/mm or mm/dd) does not matter.
    Each task gets its own name, so several files scheduled for the same minute do not replace one another."""
    task_name = f"printtool-{at.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    args = subprocess.list2cmdline(command[1:])
    script = (
        "$a = New-ScheduledTaskAction -Execute $env:PT_EXE -Argument $env:PT_ARGS;"
        "$t = New-ScheduledTaskTrigger -Once -At ([datetime]::ParseExact($env:PT_AT, 'yyyy-MM-ddTHH:mm:ss', [Globalization.CultureInfo]::InvariantCulture));"
        "Register-ScheduledTask -TaskName $env:PT_NAME -Action $a -Trigger $t -Force | Out-Null"
    )
    env = dict(os.environ, PT_EXE=command[0], PT_ARGS=args, PT_AT=at.strftime("%Y-%m-%dT%H:%M:%S"), PT_NAME=task_name)
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, env=env)
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
