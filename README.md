# printtool

Prints PDFs straight to paper, one file or a whole batch, without opening a viewer or a print dialog per file.

![printtool GUI on Windows with files, a zip and a nested zip queued](docs/printtool-screenshot.png)

## Features

- One set of settings (printer, copy count, sides, pages per sheet and its grid, paper size, page range, fit to page) applies to a whole batch; any queued file can override it. Both sides (long edge) is the default.
- Files, folders and zips (nested zips included) can be included by button or by drag and drop; zip members are extracted only when printed.
- A folder or zip row has its own checkbox; light blue marks a group printed only in part, or a file with a page range.
- "Print this" and "Print all" sit under the queue, with a progress bar showing the file printing now and its pages.
- A queue can be paused, reordered, retried, or handed to the OS scheduler to print later.
- A network printer can be included by IP address.

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

Defaults live in a hand-editable `settings.yaml` (`printtool settings-path` prints its location). The "Printable formats..." button above the queue chooses which formats count as printable; only PDF is on by default.

## Usage

```bash
printtool print report.pdf invoice.pdf --printer "Office Printer" --copies 2 --duplex long_edge
printtool batch-folder ./to-print --recursive --paper A4
printtool list-printers
printtool-gui
```

## Acknowledgement

The printer icon is [mono printer](https://openclipart.org/detail/198310/mono-printer) from openclipart.org (CC0). [SumatraPDF](https://www.sumatrapdfreader.org/) (GPLv3) prints on Windows; it is downloaded separately and not part of this repository. Created with Anthropic's Claude.
