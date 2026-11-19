"""Reusable settings editor widget: used both as the "global settings" panel
and inside the per-file override dialog, so the two never drift apart.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QScrollArea,
    QLabel,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QToolButton,
    QWidget,
)

from ..core.models import Duplex, Orientation, PrintSettings
from ..core.settings import default_print_settings


class SettingsWidget(QWidget):
    def __init__(self, printers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.printer_combo = QComboBox()
        self.printer_combo.addItem("System default", None)
        for name in printers:
            self.printer_combo.addItem(name, name)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 999)
        self.copies_spin.setValue(1)

        self.duplex_combo = QComboBox()
        duplex_labels = {Duplex.NONE: "One", Duplex.LONG_EDGE: "Both (long edge)", Duplex.SHORT_EDGE: "Both (short edge)"}
        for d in Duplex:
            self.duplex_combo.addItem(duplex_labels[d], d)

        # Pages per sheet: A number (1 by default); above 1 the grid choice
        # opens with the layouts that fit that number.
        self.nup_spin = QSpinBox()
        self.nup_spin.setRange(1, 10)
        self.nup_spin.setFixedWidth(84)
        self.nup_spin.setValue(1)
        # Each layout is shown as a small drawing of the sheet, with its
        # pages numbered in reading order.
        self.grid_combo = QComboBox()
        self.grid_combo.setIconSize(QSize(18, 22))
        self.grid_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.grid_combo.setEnabled(False)
        self.lines_rows = QCheckBox("Between rows")
        self.lines_cols = QCheckBox("Between columns")
        self.lines_frame = QCheckBox("Frame each page")
        for box in (self.lines_rows, self.lines_cols, self.lines_frame):
            box.setEnabled(False)
            box.toggled.connect(lambda _on: self._sync_grids(self.nup_spin.value(), keep=True))
        self.nup_spin.valueChanged.connect(self._sync_grids)
        self._sync_grids(1)

        self.paper_edit = QLineEdit()
        self.paper_edit.setPlaceholderText("e.g., A4, Letter (blank = printer default)")

        self.orientation_combo = QComboBox()
        orientation_labels = {Orientation.AUTO: "Automatic"}
        for o in Orientation:
            self.orientation_combo.addItem(orientation_labels.get(o, o.value.title()), o)

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText('e.g., 1-3,5 (blank = all pages)')

        self.fit_check = QCheckBox("Fit to page")
        self.fit_check.setChecked(True)

        # Collate only matters with more than one copy: Off for one copy,
        # switched on (and preset) as soon as the count goes above one.
        self.collate_check = QCheckBox("Collate")
        self.collate_check.setToolTip("With several copies, print whole sets (1-2-3, 1-2-3) instead of 1-1, 2-2, 3-3.")
        self.copies_spin.valueChanged.connect(self._sync_collate)

        self.buffer_copy_check = QCheckBox("Copy to a temporary file before printing")
        self.buffer_copy_check.setToolTip(
            "Protects against removable media (e.g., a USB drive) being pulled mid-job."
        )

        self.delete_after_print_check = QCheckBox("Delete original file after printing")
        self.delete_after_print_check.setToolTip(
            "Deletes the original file on disk once it prints successfully. A file printed from "
            "inside a zip is left untouched -- only its extracted temporary copy is affected."
        )

        advanced_toggle = QToolButton()
        advanced_toggle.setText("Advanced options")
        advanced_toggle.setCheckable(True)
        advanced_toggle.setChecked(False)
        advanced_toggle.setArrowType(Qt.RightArrow)
        advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.mirror_lr_check = QCheckBox("Mirror left-right")
        self.mirror_tb_check = QCheckBox("Mirror top-bottom")
        # Added to each page; on a sheet of several pages each shrinks with
        # its page.
        self.stamp_date_check = QCheckBox("Date and time")
        self.page_numbers_check = QCheckBox("Page numbers")
        self.signature_check = QCheckBox("Signature")
        self.signature_path = ""
        self.signature_check.toggled.connect(self._choose_signature)
        # For the whole queue.
        self.order_combo = QComboBox()
        self.order_combo.addItem("One file after another", "files")
        self.order_combo.addItem("One copy of each file in turn", "copies")
        self.order_combo.addItem("Page 1 of every file, then page 2, ...", "pages")
        self.share_sheets_check = QCheckBox("Start a file on the back of the previous file's last sheet")
        self.eject_check = QCheckBox("Remove the drive (e.g., a pen drive) after printing")
        from ..core import settings as _settings

        saved = _settings.load_defaults()
        self.order_combo.setCurrentIndex(max(0, self.order_combo.findData(saved.get("print_order", "files"))))
        self.share_sheets_check.setChecked(bool(saved.get("share_sheets", False)))
        self.eject_check.setChecked(bool(saved.get("eject_after_print", False)))
        self.order_combo.currentIndexChanged.connect(lambda _i: _settings.save_defaults({"print_order": self.order_combo.currentData()}))
        self.share_sheets_check.toggled.connect(lambda on: _settings.save_defaults({"share_sheets": on}))
        self.eject_check.toggled.connect(lambda on: _settings.save_defaults({"eject_after_print": on}))
        # A larger, scrollable drawing of the chosen layout, so long strips
        # (1 x 10) stay readable without the window growing.
        self.grid_preview = QLabel()
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidget(self.grid_preview)
        self.grid_scroll.setFixedSize(64, 40)
        self.grid_scroll.setAlignment(Qt.AlignCenter)
        self.grid_combo.currentIndexChanged.connect(lambda _i: self._draw_preview())

        advanced_box = QWidget()
        advanced_layout = QFormLayout(advanced_box)
        advanced_layout.addRow(self.buffer_copy_check)
        advanced_layout.addRow(self.delete_after_print_check)
        advanced_layout.addRow(self.mirror_lr_check)
        advanced_layout.addRow(self.mirror_tb_check)
        marks = QHBoxLayout()
        marks.addWidget(QLabel("On each page"))
        for box in (self.stamp_date_check, self.page_numbers_check, self.signature_check):
            marks.addWidget(box)
        marks.addStretch()
        advanced_layout.addRow(marks)
        order_row = QHBoxLayout()
        order_row.addWidget(QLabel("Order"))
        order_row.addWidget(self.order_combo, 1)
        advanced_layout.addRow(order_row)
        advanced_layout.addRow(self.share_sheets_check)
        advanced_layout.addRow(self.eject_check)
        # Only for several pages per sheet.
        self._grid_lines = QWidget()
        lines_row = QHBoxLayout(self._grid_lines)
        lines_row.setContentsMargins(0, 0, 0, 0)
        lines_row.addWidget(QLabel("Grid lines"))
        lines_row.addWidget(self.lines_rows)
        lines_row.addWidget(self.lines_cols)
        lines_row.addStretch()
        advanced_layout.addRow(self._grid_lines)
        advanced_layout.addRow(self.lines_frame)
        advanced_box.setVisible(False)

        def _toggle_advanced(checked: bool) -> None:
            advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
            advanced_box.setVisible(checked)

        advanced_toggle.toggled.connect(_toggle_advanced)

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addRow("Printer", self.printer_combo)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copies_spin, 1)
        copy_row.addWidget(self.collate_check)
        layout.addRow("Copy", copy_row)
        layout.addRow("Sides", self.duplex_combo)
        nup_row = QHBoxLayout()
        nup_row.addWidget(self.nup_spin)
        nup_row.addWidget(QLabel("Layout"))
        nup_row.addWidget(self.grid_combo)
        nup_row.addWidget(self.grid_scroll)
        nup_row.addStretch()
        layout.addRow("Pages per sheet", nup_row)

        layout.addRow("Paper size", self.paper_edit)
        layout.addRow("Orientation", self.orientation_combo)
        layout.addRow("Page range", self.pages_edit)
        layout.addRow(self.fit_check)
        layout.addRow(advanced_toggle)
        layout.addRow(advanced_box)

        self._sync_grids(self.nup_spin.value())
        self.load_settings(default_print_settings())

    def _draw_preview(self) -> None:
        grid = self.grid_combo.currentData()
        if not grid:
            return
        cols, rows = grid
        cw, ch = 11, 14
        pix = QPixmap(cols * cw + 4, rows * ch + 4)
        pix.fill(QColor("white"))
        p = QPainter(pix)
        font = QFont()
        font.setPixelSize(8)
        p.setFont(font)
        n = self.nup_spin.value()
        for k in range(cols * rows):
            x, y = 2 + (k % cols) * cw, 2 + (k // cols) * ch
            p.setPen(QColor("#aab"))
            p.drawRect(x, y, cw - 1, ch - 1)
            if k < n:
                p.fillRect(x + 1, y + 1, cw - 2, ch - 2, QColor("#dfe8f6"))
                p.setPen(QColor("#335"))
                p.drawText(x, y, cw, ch, Qt.AlignCenter, str(k + 1))
        p.end()
        self.grid_preview.setPixmap(pix)
        self.grid_preview.resize(pix.size())
        self.grid_preview.setToolTip(f"{cols} columns \u00d7 {rows} rows")

    def _choose_signature(self, on: bool) -> None:
        if not on:
            return
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "Signature", self.signature_path, "Images (*.png *.jpg *.jpeg)")
        if path:
            self.signature_path = path
            self.signature_check.setToolTip(path)
        elif not self.signature_path:
            self.signature_check.setChecked(False)

    def _lines(self) -> tuple[str, ...]:
        return tuple(name for name, box in (("rows", self.lines_rows), ("columns", self.lines_cols), ("frame", self.lines_frame)) if box.isChecked())

    def _sheet_icon(self, per_sheet: int, cols: int, rows: int) -> QIcon:
        """A portrait sheet with its cells, numbered in reading order, and
        the chosen lines."""
        w, h = 18, 22
        pix = QPixmap(w, h)
        pix.fill(QColor("white"))
        p = QPainter(pix)
        p.setPen(QColor("#888"))
        p.drawRect(0, 0, w - 1, h - 1)
        cw, ch = (w - 4) / cols, (h - 4) / rows
        font = QFont()
        font.setPixelSize(max(6, int(min(cw, ch) * 0.55)))
        p.setFont(font)
        lines = self._lines()
        for k in range(cols * rows):
            c, r = k % cols, k // cols
            x, y = 2 + c * cw, 2 + r * ch
            if k < per_sheet:
                p.fillRect(int(x + 1), int(y + 1), int(cw - 2), int(ch - 2), QColor("#dfe8f6"))
                p.setPen(QColor("#335"))
                p.drawText(int(x), int(y), int(cw), int(ch), Qt.AlignCenter, str(k + 1))
            if "frame" in lines:
                p.setPen(QColor("#444"))
                p.drawRect(int(x + 1), int(y + 1), int(cw - 2), int(ch - 2))
        p.setPen(QColor("#444"))
        if "columns" in lines:
            for c in range(1, cols):
                p.drawLine(int(2 + c * cw), 2, int(2 + c * cw), h - 3)
        if "rows" in lines:
            for r in range(1, rows):
                p.drawLine(2, int(2 + r * ch), w - 3, int(2 + r * ch))
        p.end()
        return QIcon(pix)

    def _sync_grids(self, per_sheet: int, keep: bool = False) -> None:
        from ..core.pages import grids_for

        chosen = self.grid_combo.currentData() if keep else None
        self.grid_combo.blockSignals(True)
        self.grid_combo.clear()
        for cols, rows in grids_for(per_sheet):
            # The drawing says it all; the size stays as a tooltip.
            self.grid_combo.addItem(self._sheet_icon(per_sheet, cols, rows), "", (cols, rows))
            self.grid_combo.setItemData(self.grid_combo.count() - 1, f"{cols} columns \u00d7 {rows} rows", Qt.ToolTipRole)
        if chosen is not None:
            self.grid_combo.setCurrentIndex(max(0, self.grid_combo.findData(chosen)))
        self.grid_combo.blockSignals(False)
        many = per_sheet > 1
        self.grid_combo.setEnabled(many)
        for box in (self.lines_rows, self.lines_cols, self.lines_frame):
            box.setEnabled(many)
            if not many:
                box.setChecked(False)
        if hasattr(self, "grid_scroll"):
            self.grid_scroll.setVisible(many)
            self._draw_preview()
        if hasattr(self, "_grid_lines"):
            self._grid_lines.setVisible(many)
            self.lines_frame.setVisible(many)

    def _sync_collate(self, copies: int) -> None:
        many = copies > 1
        if many and not self.collate_check.isEnabled():
            self.collate_check.setChecked(True)
        if not many:
            self.collate_check.setChecked(False)
        self.collate_check.setEnabled(many)

    def refresh_printers(self, printers: list[str], default: str | None) -> None:
        current = self.printer_combo.currentData()
        self.printer_combo.clear()
        self.printer_combo.addItem("System default", None)
        for name in printers:
            self.printer_combo.addItem(name, name)
        target = current if current in printers else default
        if target:
            index = self.printer_combo.findData(target)
            if index >= 0:
                self.printer_combo.setCurrentIndex(index)

    def to_settings(self) -> PrintSettings:
        return PrintSettings(
            printer=self.printer_combo.currentData(),
            copies=self.copies_spin.value(),
            duplex=self.duplex_combo.currentData(),
            paper_size=self.paper_edit.text().strip() or None,
            orientation=self.orientation_combo.currentData(),
            page_range=self.pages_edit.text().strip() or None,
            fit_to_page=self.fit_check.isChecked(),
            collate=self.collate_check.isChecked() if self.copies_spin.value() > 1 else True,
            buffer_copy=self.buffer_copy_check.isChecked(),
            delete_after_print=self.delete_after_print_check.isChecked(),
            mirror_lr=self.mirror_lr_check.isChecked(),
            mirror_tb=self.mirror_tb_check.isChecked(),
            stamp_date=self.stamp_date_check.isChecked(),
            page_numbers=self.page_numbers_check.isChecked(),
            signature=self.signature_path if self.signature_check.isChecked() and self.signature_path else None,
            pages_per_sheet=self.nup_spin.value(),
            pages_grid=self.grid_combo.currentData() if self.nup_spin.value() > 1 else None,
            pages_lines=self._lines() if self.nup_spin.value() > 1 else (),
        )

    def load_settings(self, settings: PrintSettings) -> None:
        index = self.printer_combo.findData(settings.printer)
        self.printer_combo.setCurrentIndex(index if index >= 0 else 0)
        self.copies_spin.setValue(settings.copies)
        self.duplex_combo.setCurrentIndex(self.duplex_combo.findData(settings.duplex))
        self.paper_edit.setText(settings.paper_size or "")
        self.orientation_combo.setCurrentIndex(self.orientation_combo.findData(settings.orientation))
        self.pages_edit.setText(settings.page_range or "")
        self.fit_check.setChecked(settings.fit_to_page)
        many = self.copies_spin.value() > 1
        self.collate_check.setEnabled(many)
        self.collate_check.setChecked(settings.collate and many)
        self.buffer_copy_check.setChecked(settings.buffer_copy)
        self.delete_after_print_check.setChecked(settings.delete_after_print)
        self.mirror_lr_check.setChecked(settings.mirror_lr)
        self.mirror_tb_check.setChecked(settings.mirror_tb)
        self.stamp_date_check.setChecked(settings.stamp_date)
        self.page_numbers_check.setChecked(settings.page_numbers)
        self.signature_path = settings.signature or ""
        self.signature_check.blockSignals(True)
        self.signature_check.setChecked(bool(settings.signature))
        self.signature_check.blockSignals(False)
        self.nup_spin.setValue(settings.pages_per_sheet)
        self.lines_rows.setChecked("rows" in settings.pages_lines)
        self.lines_cols.setChecked("columns" in settings.pages_lines)
        self.lines_frame.setChecked("frame" in settings.pages_lines)
        if settings.pages_grid:
            self.grid_combo.setCurrentIndex(max(0, self.grid_combo.findData(tuple(settings.pages_grid))))
