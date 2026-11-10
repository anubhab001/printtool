"""Register a network printer by IP address, so users don't have to go
through OS-specific printer-setup UIs first.

Linux/macOS: uses CUPS "driverless" IPP Everywhere, which covers the vast
majority of printers made since ~2015. Falls back to raw socket (port 9100)
for older printers that don't speak IPP.

Windows: uses the built-in "IPP Class Driver" via PowerShell's Add-Printer,
which covers the same IPP-capable printers without needing a vendor driver.

This is best-effort setup, not a replacement for a printer's own driver
when advanced features (e.g. stapling) are needed -- those should still be
installed through the OS.
"""

from __future__ import annotations

import subprocess
import sys


def add_network_printer(name: str, ip: str, protocol: str = "ipp", port: int | None = None) -> tuple[bool, str]:
    if sys.platform.startswith("win"):
        return _add_windows(name, ip, protocol, port)
    return _add_cups(name, ip, protocol, port)


def _add_cups(name: str, ip: str, protocol: str, port: int | None) -> tuple[bool, str]:
    if protocol == "socket":
        uri = f"socket://{ip}:{port or 9100}"
    else:
        uri = f"ipp://{ip}:{port or 631}/ipp/print"

    cmd = ["lpadmin", "-p", name, "-E", "-v", uri]
    if protocol == "ipp":
        cmd += ["-m", "everywhere"]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, proc.stderr.strip() or f"exit code {proc.returncode}"
    return True, f"Printer '{name}' added via {uri}"


def _add_windows(name: str, ip: str, protocol: str, port: int | None) -> tuple[bool, str]:
    port_name = f"{name}_port"
    resolved_port = port or (9100 if protocol == "socket" else 631)
    protocol_ps = "RAW" if protocol == "socket" else "IPP"

    script = (
        f"Add-PrinterPort -Name '{port_name}' -PrinterHostAddress '{ip}' "
        f"-PortNumber {resolved_port} -ErrorAction Stop; "
        f"Add-Printer -Name '{name}' -PortName '{port_name}' "
        f"-DriverName 'Microsoft IPP Class Driver' -ErrorAction Stop"
    )
    if protocol_ps == "RAW":
        script = script.replace("'Microsoft IPP Class Driver'", "'Generic / Text Only'")

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        return False, detail
    return True, f"Printer '{name}' added at {ip}:{resolved_port}"
