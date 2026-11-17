"""printtool CLI: print one or more PDFs, or every PDF in a folder, without
opening a viewer -- same settings for everything, or per-file overrides via
multiple invocations.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from . import __version__
from .core import backend, network_printer, schedule
from .core.archive import extract_all
from .core.discovery import find_printable_files
from .core.models import Duplex, Orientation, PrintSettings
from .core.settings import default_print_settings, ensure_settings_file, load_extensions


def _settings_options(f):
    defaults = default_print_settings()
    f = click.option("--printer", default=None, help="Printer name (default: system default printer).")(f)
    f = click.option("--copies", default=1, show_default=True, type=int, help="Number of copies.")(f)
    f = click.option(
        "--duplex",
        type=click.Choice([d.value for d in Duplex]),
        default=defaults.duplex.value,
        show_default=True,
        help="Duplex mode.",
    )(f)
    f = click.option("--paper", default=None, help='Paper size, e.g. "A4" or "Letter".')(f)
    f = click.option(
        "--orientation",
        type=click.Choice([o.value for o in Orientation]),
        default=defaults.orientation.value,
        show_default=True,
    )(f)
    f = click.option("--pages", default=None, help='Page range, e.g. "1-3,5".')(f)
    f = click.option("--fit/--no-fit", default=defaults.fit_to_page, show_default=True, help="Scale page to fit paper.")(f)
    f = click.option("--collate/--no-collate", default=defaults.collate, show_default=True)(f)
    f = click.option(
        "--buffer-copy/--no-buffer-copy",
        default=defaults.buffer_copy,
        show_default=True,
        help="Copy to a temporary file before printing (protects against removable media being pulled mid-job).",
    )(f)
    f = click.option(
        "--delete-after-print/--no-delete-after-print",
        default=defaults.delete_after_print,
        show_default=True,
        help="Delete the original file once it has printed successfully.",
    )(f)
    return f


def _build_settings(
    printer, copies, duplex, paper, orientation, pages, fit, collate, buffer_copy, delete_after_print
) -> PrintSettings:
    return PrintSettings(
        printer=printer,
        copies=copies,
        duplex=Duplex(duplex),
        paper_size=paper,
        orientation=Orientation(orientation),
        page_range=pages,
        fit_to_page=fit,
        collate=collate,
        buffer_copy=buffer_copy,
        delete_after_print=delete_after_print,
    )


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Print PDFs directly, in batch, or from a whole folder -- no viewer window."""
    ensure_settings_file()


@main.command("settings-path")
def settings_path_cmd() -> None:
    """Print the path to settings.yaml, a plain file meant to be hand-edited."""
    click.echo(str(ensure_settings_file()))


@main.command("print")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@_settings_options
@click.option("--dry-run", is_flag=True, help="Show what would be printed without printing.")
def print_cmd(files, printer, copies, duplex, paper, orientation, pages, fit, collate, buffer_copy, delete_after_print, dry_run):
    """Print one or more files with the same settings."""
    settings = _build_settings(printer, copies, duplex, paper, orientation, pages, fit, collate, buffer_copy, delete_after_print)
    _run(files, settings, dry_run)


@main.command("batch-folder")
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path), default=".")
@click.option("--recursive", is_flag=True, help="Include files in subfolders.")
@click.option(
    "--ext",
    default=None,
    help="Comma-separated extensions to include (without dots); defaults to settings.yaml's printable_extensions.",
)
@click.option("--advanced", is_flag=True, help="Also include settings.yaml's advanced_extensions.")
@_settings_options
@click.option("--dry-run", is_flag=True, help="Show what would be printed without printing.")
def batch_folder_cmd(
    folder, recursive, ext, advanced, printer, copies, duplex, paper, orientation, pages, fit, collate, buffer_copy, delete_after_print, dry_run
):
    """Print every printable file found in FOLDER (the current folder by default) with the same settings."""
    extensions = (
        {e.strip().lower().lstrip(".") for e in ext.split(",") if e.strip()}
        if ext
        else load_extensions(advanced=advanced)
    )
    files = find_printable_files(folder, extensions, recursive=recursive)
    for zip_path in sorted(Path(folder).glob("**/*.zip" if recursive else "*.zip")):
        extracted = extract_all(zip_path, extensions)
        if extracted:
            click.echo(f"{zip_path}: extracting {len(extracted)} file(s) (nested zips included)")
            files += extracted
    if not files:
        click.echo(f"No printable files found in {folder}")
        return
    settings = _build_settings(printer, copies, duplex, paper, orientation, pages, fit, collate, buffer_copy, delete_after_print)
    _run(files, settings, dry_run)


@main.command("list-printers")
def list_printers_cmd():
    """List detected printers and the system default."""
    printers = backend.list_printers()
    default = backend.default_printer()
    if not printers:
        click.echo("No printers detected (or printer listing is unsupported on this system).")
        return
    for name in printers:
        marker = " (default)" if name == default else ""
        click.echo(f"{name}{marker}")


@main.command("add-printer")
@click.option("--name", required=True, help="Name to register the printer under.")
@click.option("--ip", required=True, help="Printer's IP address.")
@click.option("--protocol", type=click.Choice(["ipp", "socket"]), default="ipp", show_default=True)
@click.option("--port", type=int, default=None, help="Override the default port (631 for ipp, 9100 for socket).")
def add_printer_cmd(name, ip, protocol, port):
    """Register a network printer by IP address (driverless IPP by default)."""
    success, message = network_printer.add_network_printer(name, ip, protocol, port)
    click.echo(message)
    if not success:
        raise SystemExit(1)


@main.command("schedule", context_settings={"ignore_unknown_options": True})
@click.option("--at", "at_str", required=True, help='When to print, as "YYYY-MM-DD HH:MM".')
@click.argument("subcommand_args", nargs=-1, type=click.UNPROCESSED)
def schedule_cmd(at_str, subcommand_args):
    """Schedule a PRINT or BATCH-FOLDER command (with all its own flags) to
    run later through the OS's own scheduler, so it still runs even if
    printtool itself is closed in the meantime.

    Example: printtool schedule --at "2026-11-06 09:00" print report.pdf --printer "Office Printer"
    """
    try:
        at = datetime.strptime(at_str, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise click.BadParameter('expected format "YYYY-MM-DD HH:MM"', param_hint="--at") from exc
    if not subcommand_args:
        raise click.UsageError("provide the command to run later, e.g. 'print report.pdf --printer X'")

    success, message = schedule.schedule_print(at, list(subcommand_args))
    click.echo(message)
    if not success:
        raise SystemExit(1)


def _run(files, settings: PrintSettings, dry_run: bool) -> None:
    exit_code = 0
    for path in files:
        if dry_run:
            click.echo(f"[dry-run] would print: {path}")
            continue
        result = backend.print_file(path, settings)
        if result.success:
            click.echo(f"OK    {path}")
        else:
            click.echo(f"FAIL  {path}: {result.message}", err=True)
            exit_code = 1
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
