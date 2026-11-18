# printtool

Prints PDFs straight to paper, one file or a whole batch, without opening a viewer or a print dialog per file.

![printtool GUI on Windows with files, a zip and a nested zip queued](docs/printtool-screenshot.png)

## Features

- One set of settings (printer, copies, duplex, paper size, page range, fit to page) applies to a whole batch; any queued file can override it.
- Files, folders and zips (nested zips included) can be added by button or by drag and drop; zip members are extracted only when printed.
- A queue can be paused, reordered, retried, or handed to the OS scheduler to print later.
- A network printer can be added by IP address.

## Mechanism

| OS | Engine |
|----|--------|
| Windows | [SumatraPDF](https://www.sumatrapdfreader.org/) portable, fetched by `scripts/fetch_sumatra.py` and not bundled |
| Linux, macOS | CUPS (`lp`) |

## Install

```bash
pip install -e ".[gui]"
python scripts/fetch_sumatra.py   # Windows only, once
```

Defaults live in a hand-editable `settings.yaml` (`printtool settings-path` prints its location). The GUI's View → File types window chooses which formats count as printable; only PDF is on by default.

## Usage

```bash
printtool print report.pdf invoice.pdf --printer "Office Printer" --copies 2 --duplex long_edge
printtool batch-folder ./to-print --recursive --paper A4
printtool list-printers
printtool-gui
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

---

Created with Anthropic's Claude.
