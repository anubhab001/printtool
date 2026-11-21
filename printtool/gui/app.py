from __future__ import annotations

import dataclasses
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFileInfo, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileIconProvider,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core import device
from ..core import archive, backend, discovery, network_printer, pages, preview, schedule as schedule_core
from ..core import settings
from ..core.settings import ensure_settings_file
from ..core.cli_args import settings_to_args
from ..core.models import Duplex, JobStatus, PrintJob, PrintSettings
from .folder_picker import FolderPickerDialog
from .queue_list import (
    JOB_ID_ROLE,
    STATUS_GLYPH_ROLE,
    STATUS_GLYPHS,
    ZIP_GROUP_HEADER_ROLE,
    ZIP_GROUP_ROLE,
    QueueList,
    RemoveDropZone,
    StatusGlyphDelegate,
)
from .resources import asset_path
from .widgets import SettingsWidget

_ICON_PROVIDER = QFileIconProvider()


def _n(count, word: str) -> str:
    """Singular for 0 and 1, plural from 2 on."""
    return word if (count or 0) <= 1 else word + "s"
_INDENT = "  "
GROUP_HEADER_ROLE = Qt.UserRole + 10


def _depth(text: str) -> int:
    return (len(text) - len(text.lstrip(_INDENT[0]))) // len(_INDENT)


class PrintWorker(QThread):
    job_status = Signal(str, str, str)  # path, status value, message
    finished_all = Signal()

    def __init__(self, jobs: list[PrintJob], auto_preview: bool = False) -> None:
        super().__init__()
        self._jobs = jobs
        self._auto_preview = auto_preview
        self._cancel_requested = False
        self._paused = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def cancel(self) -> None:
        self._cancel_requested = True
        self._paused = False  # a cancel while paused should still stop promptly

    def is_paused(self) -> bool:
        return self._paused

    def run(self) -> None:
        for job in self._jobs:
            while self._paused and not self._cancel_requested:
                self.msleep(150)

            if self._cancel_requested:
                job.status = JobStatus.CANCELLED
                self.job_status.emit(job.job_id, JobStatus.CANCELLED.value, "cancelled")
                continue

            job.status = JobStatus.PRINTING
            self.job_status.emit(job.job_id, JobStatus.PRINTING.value, "")
            if job.pending_extract is not None:
                zip_path, chain = job.pending_extract
                try:
                    job.path = archive.extract_leaf(zip_path, chain)
                    job.pending_extract = None
                except (KeyError, ValueError, OSError) as exc:
                    job.status = JobStatus.FAILED
                    self.job_status.emit(job.job_id, job.status.value, f"could not extract from zip: {exc}")
                    continue
            if self._auto_preview:
                preview.open_in_default_viewer(job.path)
            print_path = job.path
            # The stamp goes on each original page first, so on a sheet of
            # several pages it shrinks along with its page.
            st = job.settings
            if st.stamp_date or st.page_numbers or st.signature:
                stamped = pages.stamp_pdf(print_path, st.stamp_date, st.page_numbers, st.signature)
                if stamped is not None:
                    print_path = stamped
            if job.settings.pages_per_sheet > 1 or job.settings.pages_rows:
                laid_out = pages.nup_pdf(
                    print_path, job.settings.pages_per_sheet, job.settings.pages_grid, job.settings.pages_lines,
                    job.settings.pages_rows,
                )
                if laid_out is not None:
                    print_path = laid_out
            result = backend.print_file(print_path, job.settings)
            job.status = JobStatus.DONE if result.success else JobStatus.FAILED
            self.job_status.emit(job.job_id, job.status.value, result.message)
        self.finished_all.emit()


class FileSettingsDialog(QDialog):
    def __init__(self, title: str, settings: PrintSettings, printers: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.settings_widget = SettingsWidget(printers, self)
        self.settings_widget.load_settings(settings)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.settings_widget)
        layout.addWidget(buttons)

    def result_settings(self) -> PrintSettings:
        return self.settings_widget.to_settings()


class AddNetworkPrinterDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Include network printer by IP")

        self.name_edit = QLineEdit()
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("e.g., 192.168.1.50")
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["ipp", "socket"])
        self.port_spin = QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setValue(0)
        self.port_spin.setSpecialValueText("default")

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("IP address", self.ip_edit)
        form.addRow("Protocol", self.protocol_combo)
        form.addRow("Port", self.port_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str, int | None]:
        port = self.port_spin.value() or None
        return self.name_edit.text().strip(), self.ip_edit.text().strip(), self.protocol_combo.currentText(), port


class ScheduleDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Schedule queue for later")

        self.when_edit = QDateTimeEdit(datetime.now())
        self.when_edit.setCalendarPopup(True)
        self.when_edit.setDisplayFormat("yyyy-MM-dd HH:mm")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Print at", self.when_edit)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Every currently queued file is scheduled with its own settings."))
        layout.addWidget(buttons)

    def when(self) -> datetime:
        return self.when_edit.dateTime().toPython()


class MainWindow(QMainWindow):
    counted = Signal(str, object)  # job id, its page count (from the background)
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("printtool")
        self.setWindowIcon(QIcon(asset_path("printer-icon.png")))
        self.resize(900, 600)

        self.jobs: dict[str, PrintJob] = {}  # keyed by str(path)
        self.worker: PrintWorker | None = None
        self._print_run_started: datetime | None = None
        self._page_count_cache: dict[str, int] = {}  # job_id -> pages, filled in lazily
        # Pages are counted in the background (a large PDF takes a while);
        # the counts fill in as they come.
        from concurrent.futures.thread import ThreadPoolExecutor  # its own module: a lazily loaded package breaks in a frozen build

        self._counter = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pages")
        self._counting: set[str] = set()
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(120)
        self._count_timer.timeout.connect(self._counts_arrived)
        self.counted.connect(self._on_counted)

        printers = backend.list_printers()
        default = backend.default_printer()
        self._printers = printers  # reused by dialogs, so opening one does not re-query printers

        # --- left: queue + add buttons ---
        self.file_list = QueueList()
        self.file_list.setItemDelegate(StatusGlyphDelegate(self.file_list))
        self.file_list.itemDoubleClicked.connect(self._edit_selected_settings)
        self.file_list.files_dropped.connect(self._on_files_dropped)
        self.file_list.urls_dropped.connect(self._include_urls)
        self.file_list.files_dragged_out.connect(self._on_files_dragged_out)
        self.file_list.customContextMenuRequested.connect(self._show_queue_context_menu)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)

        self.remove_zone = RemoveDropZone()
        self.remove_zone.remove_requested.connect(self._remove_selected)

        add_files_btn = QPushButton("Include files...")
        add_files_btn.clicked.connect(self._add_files)
        add_folder_btn = QPushButton("Include folder...")
        add_folder_btn.clicked.connect(self._add_folder)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn = QPushButton("Clear all")
        clear_btn.clicked.connect(self._clear_all)
        preview_btn = QPushButton("Preview selected")
        preview_btn.clicked.connect(self._preview_selected)
        self._remove_btn, self._clear_btn, self._preview_btn = remove_btn, clear_btn, preview_btn

        file_buttons = QHBoxLayout()
        for b in (add_files_btn, add_folder_btn, remove_btn, clear_btn, preview_btn):
            file_buttons.addWidget(b)

        self.print_now_btn = QPushButton("Print this")
        self.print_now_btn.setEnabled(False)
        self.print_now_btn.clicked.connect(self._print_selected_now)
        self.print_all_btn = QPushButton("Print all")
        self.print_all_btn.setEnabled(False)
        self.print_all_btn.clicked.connect(self._print_all)

        self.queue_stats_label = QLabel()
        self.queue_stats_label.setStyleSheet("color: gray;")
        self.advanced_stats_label = QLabel()
        self.advanced_stats_label.setStyleSheet("color: gray;")
        self.advanced_stats_label.setAlignment(Qt.AlignRight)

        stats_row = QHBoxLayout()
        stats_row.addWidget(self.queue_stats_label)
        stats_row.addStretch()
        stats_row.addWidget(self.advanced_stats_label)
        for b in (self.print_now_btn, self.print_all_btn):
            b.setObjectName("primaryPrint")
            b.setMinimumWidth(96)
            stats_row.addWidget(b)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Time included (older → newer)", None)
        self.sort_combo.addItem("Time included (newer → older)", "included_reversed")
        self.sort_combo.addItem("Name (A → Z)", "name")
        self.sort_combo.addItem("Name (Z → A)", "name_down")
        self.sort_combo.addItem("File size (smaller → larger)", "size_up")
        self.sort_combo.addItem("File size (larger → smaller)", "size")
        self.sort_combo.addItem("Page count (fewer → more)", "pages_up")
        self.sort_combo.addItem("Page count (more → fewer)", "pages")
        self.sort_combo.addItem("Last modified (newer → older)", "modified")
        self.sort_combo.addItem("Last modified (older → newer)", "modified_up")
        self.sort_combo.addItem("File type (A → Z)", "type")
        self.sort_combo.addItem("File type (Z → A)", "type_down")
        self.sort_combo.currentIndexChanged.connect(lambda _: self._sort_queue())
        # Wide enough for the longest choice, so the combo never changes size.
        self.sort_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.sort_combo.setFixedWidth(self.sort_combo.sizeHint().width())

        queue_header = QHBoxLayout()
        queue_header.addWidget(QLabel("Queue"))
        queue_header.addStretch()
        formats_btn = QPushButton("Printable format...")
        formats_btn.setMinimumWidth(formats_btn.fontMetrics().horizontalAdvance("Printable format...") + 24)
        formats_btn.clicked.connect(self._edit_file_types)
        queue_header.addWidget(formats_btn)
        queue_header.addSpacing(18)  # apart from Sorting
        self._sort_label = QLabel("Sorting")
        queue_header.addWidget(self._sort_label)
        queue_header.addWidget(self.sort_combo)

        left = QVBoxLayout()
        left.addLayout(queue_header)
        left.addWidget(self.file_list)
        left.addLayout(stats_row)
        # A short bar with the file printing now beside it (its own name
        # only, shortened in the middle when long).
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        # Room for "9999/9999 sheets", the most it shows.
        self.progress_bar.setFixedWidth(self.progress_bar.fontMetrics().horizontalAdvance("9999/9999 sheets") + 90)
        self.now_printing = QLabel()
        self.now_printing.setStyleSheet("color: gray;")
        self._progress_row = QWidget()
        pr = QHBoxLayout(self._progress_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.addWidget(self.progress_bar)
        pr.addWidget(self.now_printing, 1)
        self._progress_row.hide()
        self._file_timer = QTimer(self)
        self._file_timer.setInterval(200)
        self._file_timer.timeout.connect(
            lambda: self._fill_name(min(0.95, (datetime.now() - self._file_started).total_seconds() / self._file_seconds))
        )
        self.progress_bar.show = self._progress_row.show
        self.progress_bar.hide = self._progress_row.hide
        left.addWidget(self._progress_row)
        left.addWidget(self.remove_zone)
        left.addLayout(file_buttons)

        # --- right: global settings + print/queue controls ---
        self.settings_widget = SettingsWidget(printers, self)
        refresh_btn = QPushButton("Refresh printers")
        refresh_btn.clicked.connect(self._refresh_printers)
        add_network_printer_btn = QPushButton("Include network printer by IP...")
        add_network_printer_btn.clicked.connect(self._add_network_printer)
        apply_all_btn = QPushButton("Apply to all queued files")
        self._apply_all_btn = apply_all_btn
        apply_all_btn.clicked.connect(self._apply_global_to_all)

        settings_box = QGroupBox("Default settings")
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addWidget(self.settings_widget)
        settings_layout.addWidget(refresh_btn)
        settings_layout.addWidget(add_network_printer_btn)
        settings_layout.addWidget(apply_all_btn)

        self.print_btn = self.print_all_btn
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setEnabled(False)
        self.cancel_btn = QPushButton("Cancel queue")
        self.cancel_btn.clicked.connect(self._cancel_queue)
        self.cancel_btn.setEnabled(False)
        self.schedule_btn = QPushButton("Schedule for later...")
        self.schedule_btn.clicked.connect(self._schedule_queue)

        queue_controls = QHBoxLayout()
        for b in (self.pause_btn, self.cancel_btn):
            queue_controls.addWidget(b)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        right = QVBoxLayout()
        right.addWidget(settings_box, 1)
        right.addLayout(queue_controls)
        right.addWidget(self.schedule_btn)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        # No toolbar now: The window starts just under the menu bar.
        root_layout.setContentsMargins(9, 2, 9, 9)
        left_widget = QWidget()
        left_widget.setLayout(left)
        right_widget = QWidget()
        right_widget.setLayout(right)
        root_layout.addWidget(left_widget, stretch=2)
        root_layout.addWidget(right_widget, stretch=1)
        self.setCentralWidget(root)

        self._init_menu_bar()
        self._init_toolbar()
        self._init_shortcuts()
        self._sync_enabled()

        if default:
            self.log.appendPlainText(f"Default printer detected: {default}")
        if not printers:
            self.log.appendPlainText(
                "No printers detected yet. Click 'Refresh printers' after connecting one, "
                "or check your OS print setup."
            )

        if settings.load_auto_scan_pwd():
            self._auto_scan_pwd()

    def _auto_scan_pwd(self) -> None:
        # Unlike "Scan current folder...", this runs unattended on
        # startup, so it skips the picker dialogs (a modal prompt on
        # every launch would be more disruptive than useful) and just
        # queues what it finds directly, same extensions a manual scan
        # would default to (printable_extensions, not the advanced set).
        cwd = Path.cwd()
        extensions = settings.load_extensions(advanced=False)
        found = discovery.find_printable_files(cwd, extensions, recursive=False)
        if found:
            self._add_paths(found, label="Current folder")
        for zip_path in sorted(cwd.glob("*.zip")):
            self._handle_archive(zip_path, "Current folder")

    def _init_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction("Include files...", self._add_files)
        file_menu.addAction("Include folder...", self._add_folder)
        file_menu.addAction("Include URL...", self._ask_url)
        file_menu.addAction("Scan current folder...", self._scan_cwd)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        queue_menu = menu_bar.addMenu("&Queue")
        queue_menu.addAction("Print all", self._print_all)
        queue_menu.addAction("Schedule for later...", self._schedule_queue)
        queue_menu.addAction("Retry failed", self._retry_failed)
        queue_menu.addAction("Duplicate selected", self._duplicate_selected)
        queue_menu.addSeparator()
        queue_menu.addAction("Remove selected", self._remove_selected)
        queue_menu.addAction("Clear all", self._clear_all)

        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction("Log", self._show_log)
        view_menu.addAction("Refresh printers", self._refresh_printers)
        view_menu.addAction("Include network printer by IP...", self._add_network_printer)
        view_menu.addSeparator()
        self.auto_preview_action = view_menu.addAction("Auto-preview before printing")
        self.auto_preview_action.setCheckable(True)
        self.auto_preview_action.setChecked(settings.load_auto_preview())
        self.auto_preview_action.triggered.connect(self._on_toggle_auto_preview)
        view_menu.addSeparator()
        view_menu.addAction("Printable format...", self._edit_file_types)
        view_menu.addAction("Settings file", self._open_settings_file)

        advanced_menu = menu_bar.addMenu("&Advanced")

        scanning_menu = advanced_menu.addMenu("Detail")
        self.advanced_formats_action = scanning_menu.addAction("Show advanced file formats when scanning")
        self.advanced_formats_action.setCheckable(True)
        self.advanced_formats_action.setToolTip(
            "Also offer settings.yaml's advanced_extensions (e.g., txt, log, html) when scanning a folder or zip."
        )
        self.advanced_stats_action = scanning_menu.addAction("Show advanced print statistics")
        self.advanced_stats_action.setCheckable(True)
        self.advanced_stats_action.setToolTip(
            "Paper area and a rough ink/power estimate, assuming average page coverage -- not a measurement."
        )
        self.advanced_stats_action.triggered.connect(lambda: self._update_queue_stats())

        queue_behavior_menu = advanced_menu.addMenu("Queue behavior")
        self.blank_area_warning_action = queue_behavior_menu.addAction("Warn on mostly-blank pages before printing")
        self.blank_area_warning_action.setCheckable(True)
        self.blank_area_warning_action.setChecked(settings.load_warn_on_blank_pages())
        self.blank_area_warning_action.triggered.connect(settings.save_warn_on_blank_pages)
        self.interleave_copies_action = queue_behavior_menu.addAction(
            "Interleave copies across the queue (1,2,1,2...)"
        )
        self.interleave_copies_action.setCheckable(True)
        self.interleave_copies_action.setChecked(settings.load_interleave_copies())
        self.interleave_copies_action.setToolTip(
            "Instead of printing every copy of file A then every copy of file B, round-robin one "
            "copy of each queued file at a time until each has had all its copies."
        )
        self.interleave_copies_action.triggered.connect(settings.save_interleave_copies)
        # The Order choice beside Copy does this now (Copy by copy).
        self.interleave_copies_action.setVisible(False)

        page_extras_menu = advanced_menu.addMenu("Extra page")
        page_extras_menu.addAction("Print blank page...", self._print_blank_page)
        page_extras_menu.addAction("Print test page...", self._print_test_page)
        page_extras_menu.addSeparator()
        blank_spacer_menu = page_extras_menu.addMenu("Blank page around each file")
        self._blank_spacer_group = QActionGroup(self)
        self._blank_spacer_group.setExclusive(True)
        current_spacer = settings.load_blank_page_insertion()
        for value, label in (
            ("none", "None"),
            ("before", "Before each file"),
            ("after", "After each file"),
            ("both", "Before and after each file"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(value == current_spacer)
            action.setData(value)
            action.triggered.connect(lambda _checked, v=value: settings.save_blank_page_insertion(v))
            self._blank_spacer_group.addAction(action)
            blank_spacer_menu.addAction(action)


        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction("Guide", self._show_tip)
        help_menu.addAction("Keyboard shortcut", self._show_shortcuts)

    def _on_toggle_auto_preview(self, checked: bool) -> None:
        settings.save_auto_preview(checked)

    def _init_toolbar(self) -> None:
        style = self.style()
        # Not shown: The buttons under the queue do the same. The actions are
        # kept for the menus and for enabling with the selection.
        toolbar = QToolBar("Main")
        self._actions_holder = toolbar

        toolbar.addAction(style.standardIcon(QStyle.SP_FileDialogNewFolder), "Include files...", self._add_files)
        toolbar.addAction(style.standardIcon(QStyle.SP_DirOpenIcon), "Include folder...", self._add_folder)
        toolbar.addSeparator()
        self.preview_action = toolbar.addAction(
            style.standardIcon(QStyle.SP_FileIcon), "Open in default viewer", self._preview_selected
        )
        self.print_now_action = toolbar.addAction(
            style.standardIcon(QStyle.SP_DialogOkButton), "Print now", self._print_selected_now
        )
        toolbar.addSeparator()
        self.print_all_action = toolbar.addAction(
            style.standardIcon(QStyle.SP_DriveFDIcon), "Print all", self._print_all
        )
        self.print_all_action.setToolTip("Print all queued files")
        self.print_all_action.setEnabled(False)

        self.preview_action.setEnabled(False)
        self.print_now_action.setEnabled(False)
        self.file_list.itemSelectionChanged.connect(self._update_selection_actions)
        self.file_list.itemChanged.connect(self._on_item_changed)
        self._syncing_checks = False

    def _open_settings_file(self) -> None:
        preview.open_in_default_viewer(ensure_settings_file())

    def _edit_file_types(self) -> None:
        from .file_types import FileTypesDialog  # loaded on demand to keep startup fast

        FileTypesDialog(self._open_settings_file, self).exec()

    HELP_HTML = """
<style>
  h3 { color: #2f5fb3; margin: 14px 0 4px; }
  ul { margin: 0 0 0 -18px; }
  li { margin: 3px 0; }
  td { padding: 2px 14px 2px 0; }
  .k { font-family: Consolas, monospace; color: #333; }
  .dim { color: #666; }
</style>
<h3 id="queue">Queue</h3>
<ul>
  <li>Drag files in from a file manager, or use Include files, Include folder or Include URL.</li>
  <li>Drag a queued file onto the pink Remove strip, or out of the window, to take it out.</li>
  <li>Double click a file to give it settings of its own; right-click for more.</li>
  <li>Sorting orders the queue by time included, name, size, pages, date or type.</li>
</ul>
<h3 id="order">Order of copies</h3>
<p class="dim">Beside Copy, for the whole queue (files A and B, two copies each):</p>
<table>
  <tr><td><b>File by file</b></td><td class="k">A A B B</td><td>each file with all its copies, then the next</td></tr>
  <tr><td><b>Copy by copy</b></td><td class="k">A B A B</td><td>one copy of each file, then the next round</td></tr>
  <tr><td><b>Page by page</b></td><td class="k">A1 B1 A2 B2</td><td>page 1 of every file, then page 2</td></tr>
</table>
<ul>
  <li>Collate keeps a file's pages in sets (1 2 3, 1 2 3) rather than 1 1, 2 2, 3 3.</li>
  <li>Copies go up to 100.</li>
</ul>
<h3 id="sheet">Pages per sheet</h3>
<ul>
  <li>Choose a number, then a layout; each layout is drawn with its pages in reading order.</li>
  <li>Grid lines (between rows or columns, or a frame) are in Advanced options.</li>
</ul>
<h3 id="advanced">Advanced options</h3>
<ul>
  <li>Copy to a temporary file first (for a pen drive that may be pulled out), or delete the original after printing.</li>
  <li>Mirror, and on each page the date and time, page numbers or a signature.</li>
  <li>Start each file on the back of the sheet before it; eject the drive after printing.</li>
</ul>
<h3 id="keys">Keyboard shortcut</h3>
<table>
  <tr><td class="k">Ctrl+O</td><td>Include files</td></tr>
  <tr><td class="k">Ctrl+Shift+O</td><td>Include folder</td></tr>
  <tr><td class="k">Ctrl+U</td><td>Include URL</td></tr>
  <tr><td class="k">Ctrl+Shift+C</td><td>Scan current folder</td></tr>
  <tr><td class="k">Delete, Ctrl+X</td><td>Remove selected</td></tr>
  <tr><td class="k">Ctrl+D, Ctrl+C</td><td>Duplicate selected</td></tr>
  <tr><td class="k">Ctrl+P</td><td>Print all</td></tr>
  <tr><td class="k">Ctrl+Up, Ctrl+Down</td><td>Move selected up or down</td></tr>
</table>
"""

    def _show_help(self, section: str = "queue") -> None:
        """Help: one window of short points, opened at `section`."""
        from PySide6.QtWidgets import QDialogButtonBox, QTextBrowser

        dlg = QDialog(self)
        dlg.setWindowTitle("Help")
        dlg.resize(620, 560)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(self.HELP_HTML)
        view.scrollToAnchor(section)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dlg.accept)
        layout = QVBoxLayout(dlg)
        layout.addWidget(view)
        layout.addWidget(close)
        QTimer.singleShot(0, lambda: view.scrollToAnchor(section))
        dlg.exec()

    def _show_tip(self) -> None:
        self._show_help("queue")

    def _show_shortcuts(self) -> None:
        self._show_help("keys")

    def _init_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._add_files)
        QShortcut(QKeySequence("Ctrl+U"), self, activated=self._ask_url)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self._add_folder)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self._scan_cwd)
        QShortcut(QKeySequence("Delete"), self, activated=self._remove_selected)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self._print_all)
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self._move_selected(-1))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self._move_selected(1))
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._duplicate_selected)
        QShortcut(QKeySequence("Ctrl+C"), self, activated=self._duplicate_selected)
        QShortcut(QKeySequence("Ctrl+X"), self, activated=self._remove_selected)

    # -- queue item helpers --

    def _make_item(self, job: PrintJob) -> QListWidgetItem:
        item = QListWidgetItem(str(job.path))
        item.setData(JOB_ID_ROLE, job.job_id)
        item.setIcon(_ICON_PROVIDER.icon(QFileInfo(str(job.path))))
        item.setData(STATUS_GLYPH_ROLE, STATUS_GLYPHS.get(job.status.value))
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        pages_count = self._job_pages(job)
        item.setToolTip(f"{pages_count} {_n(pages_count, 'page')}" if pages_count is not None else "Counting pages")
        return item

    def _refresh_item_text(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            return
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            if item.data(JOB_ID_ROLE) == job_id:
                item.setData(STATUS_GLYPH_ROLE, STATUS_GLYPHS.get(job.status.value))
                item.setToolTip(job.message if job.status == JobStatus.FAILED else "")
                return

    # -- file management --

    def _log_timestamped(self, label: str, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{label} {stamp}] {message}")

    @staticmethod
    def _count_job(job: PrintJob) -> int | None:
        if job.pending_extract is not None:
            zip_path, chain = job.pending_extract
            try:
                data = archive.read_leaf_bytes(zip_path, chain)
            except (KeyError, OSError, zipfile.BadZipFile):
                data = None
            return pages.count_pages_in_bytes(data) if data is not None else None
        return pages.count_pages(job.path)

    def _job_pages(self, job: PrintJob, wait: bool = False) -> int | None:
        """The page count if known; otherwise it is counted in the background
        (None until then), or here and now with `wait`."""
        if job.job_id in self._page_count_cache:
            return self._page_count_cache[job.job_id]
        if wait:
            self._page_count_cache[job.job_id] = self._count_job(job)
            return self._page_count_cache[job.job_id]
        if job.job_id not in self._counting:
            self._counting.add(job.job_id)
            self._counter.submit(self._count_and_tell, job)
        return None

    def _count_and_tell(self, job: PrintJob) -> None:
        count = self._count_job(job)
        try:
            self.counted.emit(job.job_id, count)
        except RuntimeError:  # the window has closed meanwhile
            pass

    def _on_counted(self, job_id: str, count) -> None:
        self._counting.discard(job_id)
        self._page_count_cache[job_id] = count
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            if item.data(JOB_ID_ROLE) == job_id:
                item.setToolTip(f"{count} {_n(count, 'page')}" if count is not None else "Page count unknown")
        # Many counts arrive together: the totals and order are redone once.
        self._count_timer.start()

    def _counts_arrived(self) -> None:
        self._update_queue_stats()
        if self.sort_combo.currentData() in ("pages", "pages_up"):
            self._sort_queue()

    def _show_log(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Log")
        dialog.resize(640, 380)
        view = QPlainTextEdit(self.log.toPlainText())
        view.setReadOnly(True)
        clear = QPushButton("Clear log")
        clear.clicked.connect(lambda: (self.log.clear(), view.clear()))
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        layout.addWidget(clear)
        dialog.exec()

    def _fill_name(self, part: float) -> None:
        stop = max(0.001, min(part, 0.999))
        self.now_printing.setStyleSheet(
            "color: #333; padding: 1px 6px; border: 1px solid #c8d4e6; border-radius: 3px;"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #cfe0f7, stop:{stop:.3f} #cfe0f7,"
            f" stop:{stop + 0.0005:.4f} transparent, stop:1 transparent);"
        )

    def _sheets(self, jobs) -> int:
        """Sheets of paper the queue will use, from each file's pages per
        sheet, sides and copies."""
        share = self.settings_widget.share_sheets_check.isChecked()
        total = 0
        run: list[int] = []
        for job in jobs:
            n = self._job_pages(job) or 0
            st = job.settings
            both = st.duplex != Duplex.NONE
            if share and both:
                run.append(-(-n // max(st.pages_per_sheet, 1)) * st.copies)
            else:
                total += pages.sheets_needed([n], st.pages_per_sheet, both, st.copies)
        if run:
            total += -(-sum(run) // 2)
        return total

    def _sync_enabled(self) -> None:
        """What needs files is off with an empty queue, and what needs a
        chosen file is off without one; Default settings stay on, to be set
        before any file is in."""
        if not hasattr(self, "_clear_btn"):
            return
        has = bool(self.jobs)
        chosen = has and bool(self.file_list.selectedItems())
        running = self.worker is not None and self.worker.isRunning()
        for w in (self._clear_btn, self.sort_combo, self._sort_label, self._apply_all_btn, self.schedule_btn):
            w.setEnabled(has)
        for w in (self._remove_btn, self._preview_btn):
            w.setEnabled(chosen)
        self.remove_zone.setEnabled(has)
        if not running:
            self.print_all_btn.setEnabled(has)

    def _update_queue_stats(self) -> None:
        self._sync_enabled()
        jobs = list(self.jobs.values())
        self.print_all_btn.setEnabled(bool(jobs))
        self.print_all_action.setEnabled(bool(jobs))
        if not jobs:
            self.queue_stats_label.setText("")
            self.advanced_stats_label.setText("")
            return

        total_pages = sum(p for p in (self._job_pages(j) for j in jobs) if p is not None)
        sheets = self._sheets(jobs)
        text = f"{len(jobs)} {_n(len(jobs), 'file')}, {total_pages} {_n(total_pages, 'page')}, {sheets} {_n(sheets, 'sheet')}"

        if self._print_run_started is not None:
            done = [j for j in jobs if j.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)]
            total = len(jobs)
            elapsed = (datetime.now() - self._print_run_started).total_seconds()
            pct = 100 * len(done) / total if total else 0
            # The bar counts sheets: those of finished files out of all.
            all_sheets = max(self._sheets(jobs), 1)
            self.progress_bar.setRange(0, all_sheets)
            self.progress_bar.setValue(min(self._sheets(done), all_sheets))
            self.progress_bar.show()
            text = f"Printing: {len(done)}/{total} done ({pct:.0f}%)"
            if done and len(done) < total:
                remaining = total - len(done)
                eta_seconds = (elapsed / len(done)) * remaining
                text += f", ~{int(eta_seconds)}s remaining"

        self.queue_stats_label.setText(text)

        if self.advanced_stats_action.isChecked() and total_pages:
            paper_size = self.settings_widget.to_settings().paper_size
            area_cm2 = pages.paper_area_cm2(paper_size, total_pages)
            ink_ml, kwh = pages.rough_consumption(total_pages)
            self.advanced_stats_label.setText(f"~{area_cm2 / 10_000:.2f} m² paper, ~{ink_ml:.1f} mL ink, ~{kwh:.2f} kWh")
        else:
            self.advanced_stats_label.setText("")

    def _add_paths(self, paths: list[Path], *, label: str = "File added") -> None:
        # The same file can be queued more than once (e.g. to print it with
        # two different settings, or just twice), so jobs are keyed by a
        # generated job_id rather than by path; nothing here deduplicates,
        # but a repeat is called out in the log for visibility.
        global_settings = self.settings_widget.to_settings()
        extensions = settings.load_extensions(advanced=self.advanced_formats_action.isChecked())
        for path in paths:
            if archive.is_archive(path):
                self._handle_archive(path, label)
                continue
            if path.is_dir():
                self._scan_folder(path)
                continue
            if discovery.is_shortcut(path):
                # A shortcut queues the file it points to (the queue shows that file).
                target = discovery.shortcut_target(path)
                if target is None:
                    self._log_timestamped(label, f"{path.name} - rejected (a shortcut to nothing that exists)")
                    continue
                self._log_timestamped(label, f"{path.name} - the file it points to: {target}")
                path = target
                if target.is_dir():
                    self._scan_folder(target)
                    continue
            if not discovery.is_supported(path, extensions):
                self._log_timestamped(label, f"{path.name} - rejected (not a printable file)")
                continue
            already_queued = sum(1 for job in self.jobs.values() if job.path == path)
            job = PrintJob(path=path, settings=global_settings.clone())
            self.jobs[job.job_id] = job
            self.file_list.addItem(self._make_item(job))
            suffix = f" (already queued {already_queued}x)" if already_queued else ""
            self._log_timestamped(label, f"{path.name}{suffix}")
        self._update_queue_stats()

    def _handle_archive(self, zip_path: Path, label: str) -> None:
        # No confirmation dialog: every printable file in the zip (nested
        # zips included) is tracked as its own queue row right away,
        # indented like `tree` under the zip's own row, each individually
        # checkable; nothing is actually extracted until it is printed.
        extensions = settings.load_extensions(advanced=self.advanced_formats_action.isChecked())
        try:
            tree = archive.build_tree(zip_path, extensions)
        except (OSError, zipfile.BadZipFile) as exc:
            self._log_timestamped(label, f"{zip_path.name} - could not read zip: {exc}")
            return
        if not tree.children:
            self._log_timestamped(label, f"{zip_path.name} - no printable files found in zip")
            return

        zip_icon = _ICON_PROVIDER.icon(QFileInfo(str(zip_path)))
        zip_header = self._make_group_header(zip_icon, str(zip_path))
        group_rows = [zip_header]

        global_settings = self.settings_widget.to_settings()
        leaf_count = 0
        for prefix, node in self._tree_lines(tree):
            if node.is_zip:
                item = self._make_group_header(zip_icon, prefix + node.name, nested=True)
                group_rows.append(item)
                continue
            leaf_count += 1
            job = PrintJob(
                path=Path(*node.chain), settings=global_settings.clone(), pending_extract=(zip_path, node.chain)
            )
            self.jobs[job.job_id] = job
            item = self._make_item(job)
            item.setText(prefix + node.name)
            self.file_list.addItem(item)
            group_rows.append(item)

        for item in group_rows:
            item.setData(ZIP_GROUP_HEADER_ROLE, zip_header)

        self._log_timestamped(label, f"{zip_path} (zip, {leaf_count} {_n(leaf_count, 'file')})")
        self._update_queue_stats()

    @staticmethod
    def _tree_lines(node, depth: int = 1):
        """[(indent, child_node), ...] depth-first; each level is indented
        a little further instead of drawing `tree`-style connector lines."""
        lines = []
        for child in node.children:
            lines.append((_INDENT * depth, child))
            if child.is_zip:
                lines.extend(MainWindow._tree_lines(child, depth + 1))
        return lines

    def _make_group_header(self, icon, text: str, *, nested: bool = False) -> QListWidgetItem:
        """A zip or folder row: checkable, standing for all files under it."""
        item = QListWidgetItem(icon, text)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setData(ZIP_GROUP_ROLE, not nested)
        item.setData(GROUP_HEADER_ROLE, True)
        self.file_list.addItem(item)
        return item

    def _on_files_dropped(self, paths: list[Path]) -> None:
        self._add_paths(paths, label="File dragged")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Closing while printing: Ask; a yes stops the queue cleanly (the job
        on the printer finishes) before the window goes."""
        worker = getattr(self, "worker", None)
        if worker is not None and worker.isRunning():
            answer = QMessageBox.question(self, "Printing", "Printing is in progress. Stop the queue and close?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            worker.cancel()
            worker.wait(15000)
        for job in list(getattr(self, "_jobs_running", [])):
            job.wait(5000)
        self._counter.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    def _ask_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Include URL", "A link to a file (PDF, ...) or a web page:")
        if ok and url.strip():
            self._include_urls([url.strip()])

    def _include_urls(self, urls: list[str]) -> None:
        """Links: Printable files are downloaded to the buffer and queued; a
        web page offers the printable files it links to (or itself)."""
        from PySide6.QtCore import QThread, Signal

        from ..core import fetch

        extensions = {"." + e.lstrip(".").lower() for e in settings.load_extensions(advanced=self.advanced_formats_action.isChecked())}

        class Look(QThread):
            done = Signal(list)

            def run(self):
                out = []
                for u in urls:
                    try:
                        kind, items = fetch.look(u, extensions)
                        if kind == "file":
                            items = [str(fetch.download(items[0]))]
                        out.append((u, kind, items, ""))
                    except Exception as exc:  # the log says why; nothing is queued
                        out.append((u, "error", [], str(exc)))
                self.done.emit(out)

        job = Look(self)
        job.done.connect(self._urls_looked)
        job.finished.connect(job.deleteLater)
        self._jobs_running = getattr(self, "_jobs_running", [])
        self._jobs_running.append(job)
        job.finished.connect(lambda j=job: j in self._jobs_running and self._jobs_running.remove(j))
        self._log_timestamped("URL", ", ".join(urls))
        job.start()

    def _urls_looked(self, results: list) -> None:
        from ..core import fetch

        for url, kind, items, error in results:
            if kind == "error":
                self._log_timestamped("URL failed", f"{url}: {error}")
            elif kind in ("file", "local"):
                self._add_paths([Path(p) for p in items], label="URL included")
            elif items:
                chosen, ok = self._choose_links(url, items)
                if ok and chosen:
                    self._include_urls(chosen)
            elif self.advanced_formats_action.isChecked():
                self._add_paths([fetch.save_page(url)], label="Web page included")
            else:
                self._log_timestamped("URL", f"{url}: no printable files linked (with advanced formats on, the page itself prints)")

    def _choose_links(self, url: str, links: list[str]) -> tuple[list[str], bool]:
        from PySide6.QtWidgets import QListWidget, QListWidgetItem

        dlg = QDialog(self)
        dlg.setWindowTitle("Printable files on the page")
        lst = QListWidget()
        for link in links:
            it = QListWidgetItem(link)
            it.setCheckState(Qt.Checked)
            lst.addItem(it)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(url))
        lay.addWidget(lst)
        lay.addWidget(box)
        dlg.resize(560, 380)
        ok = dlg.exec() == QDialog.Accepted
        return [lst.item(i).text() for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked], ok

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Include files", "", "PDF files (*.pdf)")
        self._add_paths([Path(f) for f in files])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Include folder")
        if folder:
            self._scan_folder(Path(folder))

    def _scan_cwd(self) -> None:
        self._scan_folder(Path.cwd())

    def _scan_folder(self, folder: Path) -> None:
        dialog = FolderPickerDialog(folder, self, advanced=self.advanced_formats_action.isChecked())
        if dialog.exec() != QDialog.Accepted:
            return
        files = dialog.selected_files()
        if not files:
            self._log_timestamped("Folder scanned", f"{folder} - no printable files found")
            return
        self._add_folder_group(folder, files, label="Folder scanned")

    def _add_folder_group(self, folder: Path, files: list[Path], *, label: str) -> None:
        """A folder row (folder icon) with its chosen files indented under it."""
        header = self._make_group_header(self.style().standardIcon(QStyle.SP_DirIcon), str(folder))
        rows = [header]
        global_settings = self.settings_widget.to_settings()
        dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        # Subfolders get rows of their own, as nested zips do: each level is
        # indented further, files directly in a folder before its subfolders.
        def rel_of(path: Path) -> Path:
            try:
                return path.relative_to(folder)
            except ValueError:
                return Path(path.name)

        ordered = sorted(files, key=lambda f: (rel_of(f).parent.parts, rel_of(f).name.lower()))
        opened: tuple[str, ...] = ()
        for path in ordered:
            parts = rel_of(path).parent.parts
            common = 0
            while common < min(len(parts), len(opened)) and parts[common] == opened[common]:
                common += 1
            for depth in range(common, len(parts)):
                rows.append(self._make_group_header(dir_icon, _INDENT * (depth + 1) + parts[depth], nested=True))
            opened = parts
            job = PrintJob(path=path, settings=global_settings.clone())
            self.jobs[job.job_id] = job
            item = self._make_item(job)
            item.setText(_INDENT * (len(parts) + 1) + path.name)
            self.file_list.addItem(item)
            rows.append(item)
        for item in rows:
            item.setData(ZIP_GROUP_HEADER_ROLE, header)
        self._log_timestamped(label, f"{folder} (folder, {len(files)} {_n(len(files), 'file')})")
        self._update_queue_stats()

    def _sort_queue(self) -> None:
        key = self.sort_combo.currentData()

        def sort_key(block: list[QListWidgetItem]):
            leaves = [self.jobs[i.data(JOB_ID_ROLE)] for i in block if i.data(JOB_ID_ROLE) in self.jobs]
            job = leaves[0] if leaves else None
            if job is None:
                return (1, "")
            if key is None:
                return (0, job.seq)
            if key == "included_reversed":
                return (0, -job.seq)
            if key in ("name", "name_down"):
                return (0, job.path.name.lower())
            if key in ("type", "type_down"):
                # By extension (DOCX, PDF, PS, XLSX ...), then by name.
                return (0, job.path.suffix.lower().lstrip("."), job.path.name.lower())
            if key in ("size", "size_up"):
                try:
                    size = job.path.stat().st_size
                except OSError:
                    return (1, 0)
                return (0, size if key == "size_up" else -size)
            if key in ("pages", "pages_up"):
                pages_count = self._job_pages(job) or 0
                return (0, pages_count if key == "pages_up" else -pages_count)
            if key in ("modified", "modified_up"):
                try:
                    t = job.path.stat().st_mtime
                    return (0, t if key == "modified_up" else -t)
                except OSError:
                    return (1, 0)
            return (0, "")

        blocks: list[list[QListWidgetItem]] = []
        seen_headers: set[int] = set()
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            header = item.data(ZIP_GROUP_HEADER_ROLE)
            if header is not None:
                if id(header) in seen_headers:
                    continue
                seen_headers.add(id(header))
                blocks.append(self._group_rows(header))
            else:
                blocks.append([item])

        blocks.sort(key=sort_key, reverse=key in ("name_down", "type_down"))
        ordered = [item for block in blocks for item in block]
        for item in ordered:
            self.file_list.takeItem(self.file_list.row(item))
        for item in ordered:
            self.file_list.addItem(item)

    def _group_rows(self, header: QListWidgetItem) -> list[QListWidgetItem]:
        """`header` plus every row (including itself) tracked under it, in
        the order they currently sit in the list."""
        return [
            self.file_list.item(row)
            for row in range(self.file_list.count())
            if self.file_list.item(row).data(ZIP_GROUP_HEADER_ROLE) is header
        ]

    def _remove_selected(self) -> None:
        to_remove: dict[int, QListWidgetItem] = {}
        for item in self.file_list.selectedItems():
            header = item.data(ZIP_GROUP_HEADER_ROLE) if item.data(ZIP_GROUP_ROLE) else None
            group = self._group_rows(item) if item.data(ZIP_GROUP_ROLE) else self._group_rows(header) if header else [item]
            for row_item in group:
                to_remove[self.file_list.row(row_item)] = row_item

        for row_item in to_remove.values():
            self.jobs.pop(row_item.data(JOB_ID_ROLE), None)
        for row in sorted(to_remove, reverse=True):
            self.file_list.takeItem(row)

        # A zip header whose children are now all gone is left behind as
        # an empty, pointless row; drop it too.
        self._prune_empty_zip_headers()
        self._update_queue_stats()

    def _prune_empty_zip_headers(self) -> None:
        for row in reversed(range(self.file_list.count())):
            item = self.file_list.item(row)
            if item.data(ZIP_GROUP_ROLE) and not any(
                self.file_list.item(r).data(ZIP_GROUP_HEADER_ROLE) is item and r != row
                for r in range(self.file_list.count())
            ):
                self.file_list.takeItem(row)

    def _on_files_dragged_out(self, paths: list[str]) -> None:
        # The items are already gone from the list widget itself (see
        # QueueList.startDrag); only the jobs dict still needs cleaning up.
        for path in paths:
            self.jobs.pop(path, None)
        self._update_queue_stats()

    def _clear_all(self) -> None:
        self.jobs.clear()
        self.file_list.clear()
        self._update_queue_stats()

    def _duplicate_selected(self) -> None:
        items = self.file_list.selectedItems()
        for item in items:
            job = self.jobs.get(item.data(JOB_ID_ROLE))
            if job is None:
                continue
            clone = PrintJob(path=job.path, settings=job.settings.clone(), pending_extract=job.pending_extract)
            self.jobs[clone.job_id] = clone
            clone_item = self._make_item(clone)
            clone_item.setText(item.text())
            self.file_list.insertItem(self.file_list.row(item) + 1, clone_item)
        self._update_queue_stats()

    def _retry_failed(self) -> None:
        self._retry(self.jobs.keys())

    def _retry_selected(self) -> None:
        self._retry(self._selected_paths())

    def _retry(self, paths) -> None:
        for path in paths:
            job = self.jobs.get(path)
            if job is not None and job.status == JobStatus.FAILED:
                job.status = JobStatus.PENDING
                job.message = ""
                self._refresh_item_text(path)

    def _selected_paths(self) -> list[str]:
        return [item.data(JOB_ID_ROLE) for item in self.file_list.selectedItems()]

    def _move_selected(self, direction: int) -> None:
        # Any row belonging to a zip moves its whole block (header plus
        # every tracked child) together, so a child row can never end up
        # reordered away from its own header.
        blocks: list[list[QListWidgetItem]] = []
        seen_headers: set[int] = set()
        for item in self.file_list.selectedItems():
            header = item if item.data(ZIP_GROUP_ROLE) else item.data(ZIP_GROUP_HEADER_ROLE)
            if header is not None:
                if id(header) in seen_headers:
                    continue
                seen_headers.add(id(header))
                blocks.append(self._group_rows(header))
            else:
                blocks.append([item])

        blocks.sort(key=lambda block: self.file_list.row(block[0]), reverse=direction > 0)
        for block in blocks:
            rows = [self.file_list.row(i) for i in block]
            new_start = rows[0] + direction
            if new_start < 0 or rows[-1] + direction >= self.file_list.count():
                continue
            items = [self.file_list.takeItem(rows[0]) for _ in rows]
            for offset, taken in enumerate(items):
                self.file_list.insertItem(new_start + offset, taken)
                taken.setSelected(True)

    def _edit_selected_settings(self) -> None:
        items = self.file_list.selectedItems()
        if not items:
            return
        first_job = self.jobs.get(items[0].data(JOB_ID_ROLE))
        if first_job is None:
            return
        title = "Settings for selected file" if len(items) == 1 else f"Settings for {len(items)} selected files"
        dialog = FileSettingsDialog(title, first_job.settings, self._printers, self)
        if dialog.exec() == QDialog.Accepted:
            new_settings = dialog.result_settings()
            for item in items:
                job = self.jobs.get(item.data(JOB_ID_ROLE))
                if job is not None:
                    job.settings = new_settings.clone()
            self.log.appendPlainText(f"Updated settings for {len(items)} {_n(len(items), 'file')}.")
            self._refresh_check_marks()

    def _apply_global_to_all(self) -> None:
        settings = self.settings_widget.to_settings()
        for job in self.jobs.values():
            job.settings = settings.clone()
        self.log.appendPlainText(f"Applied current settings to {len(self.jobs)} queued {_n(len(self.jobs), 'file')}.")
        self._refresh_check_marks()

    def _refresh_printers(self) -> None:
        printers = backend.list_printers()
        default = backend.default_printer()
        self._printers = printers
        self.settings_widget.refresh_printers(printers, default)
        self.log.appendPlainText(f"Found {len(printers)} printer(s).")

    def _preview_selected(self) -> None:
        for item in self.file_list.selectedItems():
            job = self.jobs.get(item.data(JOB_ID_ROLE))
            if job is None:
                continue
            path = job.path
            if job.pending_extract is not None:
                zip_path, chain = job.pending_extract
                try:
                    path = archive.extract_leaf(zip_path, chain)
                except (KeyError, ValueError, OSError) as exc:
                    self.log.appendPlainText(f"Could not open {job.path.name} from zip for preview: {exc}")
                    continue
            preview.open_in_default_viewer(path)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Keeps checkboxes meaningful: a group row toggles all its files, a
        group shows light blue when only some are checked, and a file with
        a page range shows light blue since not all of its pages print."""
        if self._syncing_checks:
            return
        self._syncing_checks = True
        try:
            if item.data(GROUP_HEADER_ROLE):
                on = item.checkState() != Qt.Unchecked
                for row in self._subtree(item):
                    row.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self._refresh_check_marks()
        finally:
            self._syncing_checks = False

    def _refresh_check_marks(self) -> None:
        was = self._syncing_checks
        self._syncing_checks = True
        try:
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                job = self.jobs.get(item.data(JOB_ID_ROLE))
                if job is not None and item.checkState() != Qt.Unchecked:
                    item.setCheckState(Qt.PartiallyChecked if job.settings.page_range else Qt.Checked)
            # Deepest groups first, so an outer group sees its inner ones settled.
            for row in reversed(range(self.file_list.count())):
                item = self.file_list.item(row)
                if not item.data(GROUP_HEADER_ROLE):
                    continue
                leaves = [r for r in self._subtree(item) if r.data(JOB_ID_ROLE) in self.jobs]
                states = {r.checkState() for r in leaves}
                if states == {Qt.Unchecked}:
                    item.setCheckState(Qt.Unchecked)
                elif states == {Qt.Checked}:
                    item.setCheckState(Qt.Checked)
                elif leaves:
                    item.setCheckState(Qt.PartiallyChecked)
        finally:
            self._syncing_checks = was

    def _subtree(self, header: QListWidgetItem) -> list[QListWidgetItem]:
        """Rows indented under `header`, up to its next sibling group row."""
        rows = self._group_rows(header.data(ZIP_GROUP_HEADER_ROLE) or header)
        if header not in rows:  # still being built
            return []
        depth = _depth(header.text())
        out = []
        for row in rows[rows.index(header) + 1 :]:
            if row.data(GROUP_HEADER_ROLE) and _depth(row.text()) <= depth:
                break
            out.append(row)
        return out

    def _update_selection_actions(self) -> None:
        has_selection = bool(self.file_list.selectedItems())
        self.print_now_btn.setEnabled(has_selection)
        self.preview_action.setEnabled(has_selection)
        self.print_now_action.setEnabled(has_selection)
        self._sync_enabled()

    def _reveal_selected(self) -> None:
        for item in self.file_list.selectedItems():
            job = self.jobs.get(item.data(JOB_ID_ROLE))
            if job is not None:
                preview.reveal_in_file_manager(job.path)

    def _add_network_printer(self) -> None:
        dialog = AddNetworkPrinterDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        name, ip, protocol, port = dialog.values()
        if not name or not ip:
            QMessageBox.warning(self, "Missing info", "Both a name and an IP address are required.")
            return
        success, message = network_printer.add_network_printer(name, ip, protocol, port)
        self.log.appendPlainText(message)
        if success:
            self._refresh_printers()
        else:
            QMessageBox.warning(self, "Could not add printer", message)

    def _print_blank_page(self) -> None:
        paper_size = self.settings_widget.to_settings().paper_size
        path = pages.build_blank_pdf(paper_size)
        self._add_paths([path], label="Blank page")

    def _print_test_page(self) -> None:
        paper_size = self.settings_widget.to_settings().paper_size
        path = pages.build_test_pdf(paper_size)
        self._add_paths([path], label="Test page")

    # -- context menu --

    def _show_queue_context_menu(self, pos) -> None:
        if not self.file_list.selectedItems():
            return
        menu = QMenu(self)
        preview_action = menu.addAction("Preview")
        reveal_action = menu.addAction("Open containing folder")
        edit_action = menu.addAction("Print settings...")
        print_now_action = menu.addAction("Print now")
        retry_action = menu.addAction("Retry failed")
        duplicate_action = menu.addAction("Duplicate")
        menu.addSeparator()
        move_up_action = menu.addAction("Move up queue")
        move_down_action = menu.addAction("Move down queue")
        remove_action = menu.addAction("Remove")
        menu.addSeparator()
        pause_action = menu.addAction("Pause queue")
        resume_action = menu.addAction("Resume queue")
        cancel_action = menu.addAction("Cancel queue")

        running = self.worker is not None and self.worker.isRunning()
        print_now_action.setEnabled(not running)
        retry_action.setEnabled(
            any(self.jobs[p].status == JobStatus.FAILED for p in self._selected_paths() if p in self.jobs)
        )
        pause_action.setEnabled(running and not self._is_paused())
        resume_action.setEnabled(running and self._is_paused())
        cancel_action.setEnabled(running)

        action = menu.exec(self.file_list.mapToGlobal(pos))
        if action == preview_action:
            self._preview_selected()
        elif action == reveal_action:
            self._reveal_selected()
        elif action == edit_action:
            self._edit_selected_settings()
        elif action == print_now_action:
            self._print_selected_now()
        elif action == retry_action:
            self._retry_selected()
        elif action == duplicate_action:
            self._duplicate_selected()
        elif action == move_up_action:
            self._move_selected(-1)
        elif action == move_down_action:
            self._move_selected(1)
        elif action == remove_action:
            self._remove_selected()
        elif action == pause_action:
            self._toggle_pause()
        elif action == resume_action:
            self._toggle_pause()
        elif action == cancel_action:
            self._cancel_queue()

    # -- printing --

    @staticmethod
    def _interleave_copies(jobs: list[PrintJob]) -> list[PrintJob]:
        """Round-robin one copy of each job at a time (1,2,1,2,... instead of
        1,1,2,2,...): each round takes the jobs that still have a copy left
        and sends them with copies=1, so consecutive print calls alternate
        between files instead of finishing one file's copies before the
        next starts."""
        max_copies = max((job.settings.copies for job in jobs), default=1)
        calls = []
        for round_index in range(max_copies):
            for job in jobs:
                if round_index < job.settings.copies:
                    calls.append(dataclasses.replace(job, settings=job.settings.clone(copies=1)))
        return calls

    def _joined(self, jobs: list[PrintJob], join, what: str) -> list[PrintJob]:
        """PDF files printed as one (by `join`), with the first one's
        settings; other files follow as they are."""
        pdfs = [j for j in jobs if j.path.suffix.lower() == ".pdf" and j.pending_extract is None]
        if len(pdfs) < 2:
            return jobs
        path = join([j.path for j in pdfs])
        if path is None:
            return jobs
        self.log.appendPlainText(f"Printing {len(pdfs)} files as one ({what}).")
        merged = PrintJob(path=path, settings=pdfs[0].settings.clone(buffer_copy=False, delete_after_print=False))
        return [merged] + [j for j in jobs if j not in pdfs]

    def _bracket_blank_pages(self, jobs: list[PrintJob]) -> list[PrintJob]:
        mode = settings.load_blank_page_insertion()
        if mode == "none" or not jobs:
            return jobs
        paper_size = self.settings_widget.to_settings().paper_size
        result = []
        for job in jobs:
            if mode in ("before", "both"):
                result.append(self._make_blank_spacer_job(paper_size))
            result.append(job)
            if mode in ("after", "both"):
                result.append(self._make_blank_spacer_job(paper_size))
        return result

    @staticmethod
    def _make_blank_spacer_job(paper_size: str | None) -> PrintJob:
        path = pages.build_blank_pdf(paper_size)
        return PrintJob(path=path, settings=PrintSettings(paper_size=paper_size))

    def _print_all(self) -> None:
        if not self.jobs:
            QMessageBox.information(self, "Nothing to print", "The queue is empty.")
            return

        ordered_jobs = []
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            job = self.jobs.get(item.data(JOB_ID_ROLE))
            if job is not None and item.checkState() != Qt.Unchecked:
                ordered_jobs.append(job)
        self._start_worker(ordered_jobs)

    def _print_selected_now(self) -> None:
        items = self.file_list.selectedItems()
        if not items:
            return
        jobs = [self.jobs[item.data(JOB_ID_ROLE)] for item in items if item.data(JOB_ID_ROLE) in self.jobs]
        self._start_worker(jobs)

    def _start_worker(self, jobs: list[PrintJob]) -> None:
        if not jobs:
            return
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Already printing", "A queue is already running; pause or cancel it first.")
            return

        for job in jobs:
            job.status = JobStatus.PENDING
            self._refresh_item_text(job.job_id)

        if self.blank_area_warning_action.isChecked():
            for job in jobs:
                if job.pending_extract is None and pages.mostly_blank(job.path):
                    self.log.appendPlainText(f"Warning: {job.path.name} looks mostly blank.")

        order = self.settings_widget.order_combo.currentData()
        if (order == "copies" or self.interleave_copies_action.isChecked()) and len(jobs) > 1:
            jobs = self._interleave_copies(jobs)
        elif order == "pages" and len(jobs) > 1:
            jobs = self._joined(jobs, pages.interleave_pdfs, "pages of all files in turn")
        if self.settings_widget.share_sheets_check.isChecked() and len(jobs) > 1 and order != "pages":
            jobs = self._joined(jobs, pages.concat_pdfs, "files sharing sheets")
        self._eject_after = (
            device.removable_drives([j.path for j in jobs]) if self.settings_widget.eject_check.isChecked() else []
        )

        jobs = self._bracket_blank_pages(jobs)

        self.print_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("Pause")
        self.cancel_btn.setEnabled(True)
        self.log.appendPlainText(f"Printing {len(jobs)} {_n(len(jobs), 'file')}...")
        self._print_run_started = datetime.now()
        self._update_queue_stats()

        self.worker = PrintWorker(
            jobs,
            auto_preview=self.auto_preview_action.isChecked(),
        )
        self.worker.job_status.connect(self._on_job_status)
        self.worker.finished_all.connect(self._on_all_done)
        self.worker.start()

    def _is_paused(self) -> bool:
        return self.worker is not None and self.worker.is_paused()

    def _toggle_pause(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        if self._is_paused():
            self.worker.resume()
            self.pause_btn.setText("Pause")
            self.log.appendPlainText("Queue resumed.")
        else:
            self.worker.pause()
            self.pause_btn.setText("Resume")
            self.log.appendPlainText("Queue paused after the current file.")

    def _cancel_queue(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.log.appendPlainText("Cancelling remaining queued files...")

    def _on_job_status(self, job_id: str, status_value: str, message: str) -> None:
        job = self.jobs.get(job_id)
        if job is not None:
            job.status = JobStatus(status_value)
            job.message = message
        self._refresh_item_text(job_id)
        if job is not None and status_value == JobStatus.PRINTING.value:
            pages_note = f"pages {job.settings.page_range}" if job.settings.page_range else "all pages"
            self.progress_bar.setFormat("%v/%m sheets")
            fm = self.now_printing.fontMetrics()
            self.now_printing.setText(fm.elidedText(job.path.name, Qt.ElideMiddle, max(80, self.now_printing.width())))
            self.now_printing.setToolTip(job.path.name)
            # The name's box fills as this file prints: an estimate from its
            # pages, as the printer does not report its own progress.
            self._file_started = datetime.now()
            self._file_seconds = max(3.0, 1.5 * (self._job_pages(job) or 1))
            self._file_timer.start()
        if job is not None and status_value != JobStatus.PRINTING.value:
            self._file_timer.stop()
            self._fill_name(1.0 if status_value == JobStatus.DONE.value else 0.0)
            self.log.appendPlainText(
                f"[{status_value.upper()}] {job.path}{(' - ' + message) if message else ''}"
            )
        self._update_queue_stats()

    def _on_all_done(self) -> None:
        self.log.appendPlainText("Done.")
        for drive in getattr(self, "_eject_after", []):
            ok = device.eject(drive)
            self.log.appendPlainText(f"{'Removed' if ok else 'Could not remove'} {drive}")
        self._eject_after = []
        self.progress_bar.hide()
        self.print_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self._print_run_started = None
        self._update_queue_stats()

    # -- scheduling --

    def _schedule_queue(self) -> None:
        if not self.jobs:
            QMessageBox.information(self, "Nothing to schedule", "The queue is empty.")
            return
        dialog = ScheduleDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        at = dialog.when()

        succeeded = 0
        for job in self.jobs.values():
            path = job.path
            if job.pending_extract is not None:
                # The scheduled command runs later, standalone, with no
                # access to the original zip's queue entry -- extract now
                # so there is a real file on disk for it to print.
                zip_path, chain = job.pending_extract
                try:
                    path = archive.extract_leaf(zip_path, chain)
                except (KeyError, ValueError, OSError) as exc:
                    self.log.appendPlainText(f"Could not extract {job.path.name} from zip to schedule it: {exc}")
                    continue
            args = settings_to_args(path, job.settings)
            success, message = schedule_core.schedule_print(at, args)
            self.log.appendPlainText(message)
            if success:
                succeeded += 1
        self.log.appendPlainText(f"Scheduled {succeeded} of {len(self.jobs)} {_n(len(self.jobs), 'file')} for {at}.")


def main() -> None:
    if sys.platform.startswith("win") and not getattr(sys, "frozen", False):
        # From Python only: Windows groups a taskbar icon by this ID rather
        # than by python.exe (whose icon it would show). The exe is left to
        # Windows, which then shows the exe's own icon; an ID with no
        # shortcut behind it gave the generic one there.
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("printtool.gui")
        except Exception:
            pass

    ensure_settings_file()
    app = QApplication(sys.argv)
    # The .ico carries every size, so the taskbar and Alt+Tab get a sharp one.
    app.setWindowIcon(QIcon(asset_path("printer-icon.ico")))
    app.setStyleSheet(
        "QPushButton#primaryPrint { background: #2f6fd6; color: white; border: none; border-radius: 6px; padding: 6px 14px; font-weight: 600; }"
        "QPushButton#primaryPrint:hover { background: #3b82f0; }"
        "QPushButton#primaryPrint:pressed { background: #2459ad; }"
        "QPushButton#primaryPrint:disabled { background: #b9c7de; color: #f4f6fa; }"
    )
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
