"""Reusable settings editor widget: used both as the "global settings" panel and inside the per-file override dialog, so the two never drift apart.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from ..core.models import Duplex, Orientation, PrintSettings
from ..core.settings import default_print_settings


def _rows_key(rows) -> str:
    return "rows:" + ",".join(map(str, rows))


class _PresetBox(QComboBox):
    """A number chosen from a list (no typing), with QSpinBox's calls."""

    from PySide6.QtCore import Signal as _Signal

    valueChanged = _Signal(int)  # noqa: N815 - QSpinBox's name

    def __init__(self, values) -> None:
        super().__init__()
        for v in values:
            self.addItem(str(v), v)
        self.currentIndexChanged.connect(lambda _i: self.valueChanged.emit(self.value()))

    def value(self) -> int:
        return int(self.currentData() or 1)

    def setValue(self, v: int) -> None:  # noqa: N802 - QSpinBox's name
        i = self.findData(int(v))
        if i < 0:  # a count from elsewhere (rows of one's own): Listed too
            self.addItem(str(v), int(v))
            i = self.count() - 1
        self.setCurrentIndex(i)


class _FitPopupCombo(QComboBox):
    """Its list as tall as its choices, no empty rows after the last."""

    def showPopup(self) -> None:  # noqa: N802 - Qt override
        super().showPopup()
        view = self.view()
        rows = sum(view.sizeHintForRow(i) for i in range(self.count()))
        frame = view.parentWidget()
        if frame is not None and rows > 0:
            frame.setFixedHeight(min(rows + 2 * view.frameWidth() + 4, 620))


class SettingsWidget(QWidget):
    def __init__(self, printers: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.printer_combo = QComboBox()
        self.printer_combo.addItem("System default", None)
        for name in printers:
            self.printer_combo.addItem(name, name)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 100)
        self.copies_spin.setValue(1)
        self.copies_spin.setFixedWidth(70)

        self.duplex_combo = QComboBox()
        duplex_labels = {Duplex.NONE: "One", Duplex.LONG_EDGE: "Both (long edge)", Duplex.SHORT_EDGE: "Both (short edge)"}
        for d in Duplex:
            self.duplex_combo.addItem(duplex_labels[d], d)

        # Pages per sheet: A number (1 by default); above 1 the grid choice opens with the layouts that fit that number.
        self.nup_spin = _PresetBox((1, 2, 3, 4, 6, 8, 9, 10, 12, 16))
        self.nup_spin.setFixedWidth(70)
        # Each layout is shown as a small drawing of the sheet, with its pages numbered in reading order.
        self.grid_combo = _FitPopupCombo()
        self.grid_combo.setIconSize(QSize(18, 22))
        self.grid_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.grid_combo.setEnabled(False)
        self._rows: tuple[int, ...] = ()
        self.grid_combo.activated.connect(self._grid_chosen)
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

        # Collate only matters with more than one copy: Off for one copy, switched on (and preset) as soon as the count goes above one.
        self.collate_check = QCheckBox("Collate")
        self.collate_check.setToolTip("With several copies, print whole sets (1-2-3, 1-2-3) instead of 1-1, 2-2, 3-3.")
        self.copies_spin.valueChanged.connect(self._sync_collate)

        self.buffer_copy_check = QCheckBox("Copy to temporary file before printing")
        self.buffer_copy_check.setToolTip(
            "Protects against removable media (e.g., a USB drive) being pulled mid-job."
        )

        self.delete_after_print_check = QCheckBox("Delete original file after printing")
        self.delete_after_print_check.setToolTip(
            "Deletes the original file on disk once it prints successfully. A file printed from "
            "inside a zip is left untouched; only its extracted temporary copy is affected."
        )

        from PySide6.QtWidgets import QPushButton

        advanced_button = QPushButton("Advanced options...")

        self.mirror_lr_check = QCheckBox("Mirror left-right")
        self.mirror_tb_check = QCheckBox("Mirror top-bottom")
        from ..core.style import STYLES

        self.style_combo = QComboBox()
        for label, value in STYLES:
            self.style_combo.addItem(label, value)
        self.style_combo.setToolTip("Printing style: Each page drawn again in it (PDF only).")
        # Added to each page; on a sheet of several pages each shrinks with its page.
        self.stamp_date_check = QCheckBox("Date and time")
        self.page_numbers_check = QCheckBox("Page numbers")
        self.signature_check = QCheckBox("Signature")
        self.signature_path = ""
        self.signature_check.toggled.connect(self._choose_signature)
        # For the whole queue.
        self.order_combo = QComboBox()
        for label, key, tip in (("File by file", "files", "Each file whole, with all its copies, then the next"),
                                ("Copy by copy", "copies", "One copy of each file, then the next copy of each"),
                                ("Page by page", "pages", "Page 1 of every file, then page 2 of every file")):
            self.order_combo.addItem(label, key)
            self.order_combo.setItemData(self.order_combo.count() - 1, tip, Qt.ToolTipRole)
        self.order_combo.setToolTip("Order of the whole queue")
        self.share_sheets_check = QCheckBox("Start each file on the back of the sheet before it")
        self.eject_check = QCheckBox("Eject drive after printing (e.g., pen drive)")
        from ..core import settings as _settings

        saved = _settings.load_defaults()
        self.order_combo.setCurrentIndex(max(0, self.order_combo.findData(saved.get("print_order", "files"))))
        self.share_sheets_check.setChecked(bool(saved.get("share_sheets", False)))
        self.eject_check.setChecked(bool(saved.get("eject_after_print", False)))
        self.order_combo.currentIndexChanged.connect(lambda _i: _settings.save_defaults({"print_order": self.order_combo.currentData()}))
        self.share_sheets_check.toggled.connect(lambda on: _settings.save_defaults({"share_sheets": on}))
        self.eject_check.toggled.connect(lambda on: _settings.save_defaults({"eject_after_print": on}))
        # The list of layouts shows each one at a readable size (cells of a fixed size), inside a fixed-size list that scrolls for long strips such as 1 x 10; the closed box shows the chosen one small.
        from PySide6.QtWidgets import QListView

        popup = QListView()
        popup.setIconSize(QSize(120, 150))
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        popup.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        popup.setFixedWidth(150)
        self.grid_combo.setView(popup)
        self.grid_combo.setMaxVisibleItems(4)

        advanced_box = QWidget()
        advanced_layout = QFormLayout(advanced_box)
        advanced_layout.addRow(self.buffer_copy_check)
        advanced_layout.addRow(self.delete_after_print_check)
        advanced_layout.addRow(self.mirror_lr_check)
        advanced_layout.addRow(self.mirror_tb_check)
        advanced_layout.addRow("Style", self.style_combo)
        marks = QHBoxLayout()
        marks.addWidget(QLabel("On each page"))
        for box in (self.stamp_date_check, self.page_numbers_check, self.signature_check):
            marks.addWidget(box)
        marks.addStretch()
        advanced_layout.addRow(marks)
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
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

        self._advanced = QDialog(self)
        self._advanced.setWindowTitle("Advanced options")
        dlg_layout = QVBoxLayout(self._advanced)
        dlg_layout.addWidget(advanced_box)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self._advanced.accept)
        dlg_layout.addWidget(close)
        advanced_button.clicked.connect(self._advanced.exec)

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addRow("Printer", self.printer_combo)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copies_spin)
        copy_row.addWidget(self.collate_check)
        copy_row.addSpacing(10)
        copy_row.addWidget(QLabel("Order"))
        copy_row.addWidget(self.order_combo, 1)
        layout.addRow("Copy", copy_row)
        layout.addRow("Sides", self.duplex_combo)
        nup_row = QHBoxLayout()
        nup_row.addWidget(self.nup_spin)
        self.layout_label = QLabel("Layout")
        nup_row.addWidget(self.layout_label)
        nup_row.addWidget(self.grid_combo)
        nup_row.addStretch()
        layout.addRow("Pages per sheet", nup_row)

        layout.addRow("Paper size", self.paper_edit)
        layout.addRow("Orientation", self.orientation_combo)
        layout.addRow("Page range", self.pages_edit)
        layout.addRow(self.fit_check)
        layout.addRow(advanced_button)

        self._sync_grids(self.nup_spin.value())
        self.load_settings(default_print_settings())

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
        """The sheet with its cells (all the same size whatever the layout), numbered in reading order, with the chosen lines."""
        cw, ch = 11, 14
        w, h = cols * cw + 4, rows * ch + 4
        pix = QPixmap(w, h)
        pix.fill(QColor("white"))
        p = QPainter(pix)
        p.setPen(QColor("#888"))
        p.drawRect(0, 0, w - 1, h - 1)
        font = QFont()
        font.setPixelSize(8)
        p.setFont(font)
        lines = self._lines()
        for k in range(cols * rows):
            x, y = 2 + (k % cols) * cw, 2 + (k // cols) * ch
            if k < per_sheet:
                p.fillRect(x + 1, y + 1, cw - 2, ch - 2, QColor("#dfe8f6"))
                p.setPen(QColor("#335"))
                p.drawText(x, y, cw, ch, Qt.AlignCenter, str(k + 1))
            if "frame" in lines:
                p.setPen(QColor("#444"))
                p.drawRect(x + 1, y + 1, cw - 2, ch - 2)
        p.setPen(QColor("#444"))
        if "columns" in lines:
            for c in range(1, cols):
                p.drawLine(2 + c * cw, 2, 2 + c * cw, h - 3)
        if "rows" in lines:
            for r in range(1, rows):
                p.drawLine(2, 2 + r * ch, w - 3, 2 + r * ch)
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
        # Only the preset grids (no rows of one's own).
        if chosen is not None:
            self.grid_combo.setCurrentIndex(max(0, self.grid_combo.findData(chosen)))
        self.grid_combo.blockSignals(False)
        many = per_sheet > 1
        self.grid_combo.setEnabled(many)
        if hasattr(self, "layout_label"):
            self.layout_label.setEnabled(many)
        for box in (self.lines_rows, self.lines_cols, self.lines_frame):
            box.setEnabled(many)
            if not many:
                box.setChecked(False)
        if hasattr(self, "_grid_lines"):
            self._grid_lines.setVisible(many)
            self.lines_frame.setVisible(many)

    def _grid_chosen(self, index: int) -> None:
        return  # preset grids only
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "Rows set by hand", "Pages in each row, top to bottom (for example 2, 1):",
                                        text=", ".join(map(str, self._rows or (2, 1))))
        try:
            rows = tuple(int(x) for x in text.replace(" ", "").split(",") if x) if ok else ()
        except ValueError:
            rows = ()
        if rows and all(0 < n <= 12 for n in rows) and len(rows) <= 12:
            self._rows = rows
            self.nup_spin.blockSignals(True)
            self.nup_spin.setValue(sum(rows))
            self.nup_spin.blockSignals(False)
            self._sync_grids(sum(rows))
            self.grid_combo.setCurrentIndex(self.grid_combo.findData(_rows_key(rows)))
        else:
            self.grid_combo.setCurrentIndex(0)

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

    def _is_rows(self) -> bool:
        d = self.grid_combo.currentData()
        return isinstance(d, str) and d.startswith("rows:")

    def _is_grid(self) -> bool:
        d = self.grid_combo.currentData()
        return isinstance(d, tuple) and len(d) == 2 and all(isinstance(x, int) for x in d)

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
            style=self.style_combo.currentData() or "color",
            stamp_date=self.stamp_date_check.isChecked(),
            page_numbers=self.page_numbers_check.isChecked(),
            signature=self.signature_path if self.signature_check.isChecked() and self.signature_path else None,
            pages_per_sheet=self.nup_spin.value(),
            pages_grid=self.grid_combo.currentData() if self.nup_spin.value() > 1 and self._is_grid() else None,
            pages_rows=tuple(int(x) for x in self.grid_combo.currentData()[5:].split(",")) if self.nup_spin.value() > 1 and self._is_rows() else None,
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
        k = self.style_combo.findData(getattr(settings, "style", "color"))
        self.style_combo.setCurrentIndex(k if k >= 0 else 0)
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
