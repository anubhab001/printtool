# Changelog

## Version 7
- Sheet count beside files and pages.
- Sort by time included, name, file size or page count, either way.
- Advanced: Print order, starting a file on the back of the last sheet, removing the drive after printing; temporary copy on by default.
- Scrollable layout preview; the log moves to View > Log.

## Version 6
- "Print this" and "Print all" under the queue, beside the counts; one "Print all".
- "Include" instead of "Add"; "Copy" with Collate beside it (active above one copy); "Sides" One, Both (long edge, the default) or Both (short edge).
- Pages per sheet (1 -- 10), each layout drawn; grid lines and page frames under Advanced options.
- Advanced options: Date and time, page numbers or a signature on each page.
- "Time included" sort and its reverse; singular "file"/"page" for 0 and 1; "e.g.,".
- Grey tree lines with rounded corners for folders and zips.

## Version 5
- Queue: Zip icon for zips, folder rows for scanned folders, plain indentation instead of tree lines.
- Group checkboxes follow their files; light blue for partly printed groups or files with a page range.
- "Chronological" replaces "(Unsorted)"; "Printable formats..." button above the queue.
- Progress bar with the current file and its pages.
- View → File types: Tick which formats count as printable (only PDF by default).
- Faster startup (printers listed without PowerShell).
- Advanced menu is grouped into submenus: Blank page around each file, date/time stamp (PDF only), interleaved copies (1,2,1,2).
- "Print all" is disabled when the queue is empty.
- "(Unsorted)" label; "Print now"/"Print all" buttons above the queue.
- Zip members' page counts are read in memory ahead of extraction, so the queue stats line no longer has an "(some unknown)" case.
- Queue stats line: core counts on the left, advanced paper/ink/power estimate on the right, no separator or "rough estimate" wording.
- A zip's queue row shows its full path; its log line no longer repeats "nested zips included".
- Printing-status glyphs read as one circle filling in (empty, half, full).
- Folder/zip scans with nothing printable are rejected with a log line instead of a blocking dialog; the same applies to a dropped folder.
- Moving or removing any row that belongs to a zip now acts on the whole zip block, not just that one row; an emptied zip header is pruned.
- "Delete original file after printing" and "copy to a temporary file before printing" moved behind an "Advanced options" disclosure.
- Added Ctrl+C (duplicate) and Ctrl+X (remove) shortcuts; "Move up/down" renamed to "Move up/down queue".
- Toolbar's preview/print-now actions are disabled with nothing selected; "Print all queued files" toolbar tooltip shortened to "Print all".
- "Print queue" label renamed to "Queue".
- Queue sortable by name, size, pages or last modified; hovering a row shows its page count.
- Advanced menu: Blank-page/test-page printing, a mostly-blank-page warning before printing, and per-file left-right/top-bottom mirroring.
