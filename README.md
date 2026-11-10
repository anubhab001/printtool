# printtool

A cross-platform CLI and GUI for printing PDFs directly, without a
viewer window or a print dialog for every file.

- Printing one or more files, every printable file in a folder
  (recursive, auto-detected on startup too) or inside a `.zip` (nested
  zips included), with one shared setting or a per-file override.
- The GUI queue accepts drag-and-drop, sorts by name/size/pages/last
  modified, shows a file-type icon and a status glyph per row, a
  page-count/progress/ETA line, and duplicate/retry/reorder/pause/cancel
  from a right-click menu.
- A network printer can be registered by IP (driverless IPP by
  default); a queue can be scheduled through the OS's own scheduler.
- Advanced options (behind a disclosure, not in the way): buffer-copy,
  delete-after-print, left-right/top-bottom mirroring, a blank/test
  page, and a before-printing warning for a mostly-blank page.

## Mechanism

| OS | Engine |
|----|--------|
| Windows | [SumatraPDF](https://www.sumatrapdfreader.org/) portable, invoked silently |
| Linux, macOS | CUPS (`lp`), already part of both |

SumatraPDF is GPLv3 and not bundled; `scripts/fetch_sumatra.py` fetches
the official portable build, invoked only as a subprocess.

## Install

```bash
pip install -e ".[gui]"       # CLI and GUI
pip install -e .              # CLI only
python scripts/fetch_sumatra.py   # Windows only
```

Settings (printer, paper size, duplex, which extensions count as
printable, ...) live in a plain, hand-editable `settings.yaml`
(`printtool settings-path` prints where).

## CLI

```bash
printtool print report.pdf invoice.pdf --printer "Office Printer" --copies 2
printtool batch-folder ./to-print --recursive --paper A4 --fit
printtool list-printers
printtool add-printer --name "Front Desk" --ip 192.168.1.50
printtool schedule --at "2026-11-06 09:00" print report.pdf
```

`printtool --help` for the full flag list.

## GUI

```bash
printtool-gui
```

Files, a folder or a zip can be dragged in or added by button. The
toolbar covers add/preview/print; the right-click menu covers
settings, duplicate, retry, reorder, remove and queue pause/cancel.

## License

MIT, per [LICENSE](LICENSE). SumatraPDF, fetched separately and not
redistributed here, is GPLv3.

---

Created with Anthropic's Claude.
