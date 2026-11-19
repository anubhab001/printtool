"""Reusable settings editor widget: used both as the "global settings" panel
and inside the per-file override dialog, so the two never drift apart.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
        self.nup_spin.setRange(1, 16)
        self.nup_spin.setValue(1)
        self.grid_combo = QComboBox()
        self.grid_combo.setEnabled(False)
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

        advanced_box = QWidget()
        advanced_layout = QFormLayout(advanced_box)
        advanced_layout.addRow(self.buffer_copy_check)
        advanced_layout.addRow(self.delete_after_print_check)
        advanced_layout.addRow(self.mirror_lr_check)
        advanced_layout.addRow(self.mirror_tb_check)
        advanced_box.setVisible(False)

        def _toggle_advanced(checked: bool) -> None:
            advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
            advanced_box.setVisible(checked)

        advanced_toggle.toggled.connect(_toggle_advanced)

        layout = QFormLayout(self)
        layout.addRow("Printer", self.printer_combo)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copies_spin, 1)
        copy_row.addWidget(self.collate_check)
        layout.addRow("Copy", copy_row)
        layout.addRow("Sides", self.duplex_combo)
        nup_row = QHBoxLayout()
        nup_row.addWidget(self.nup_spin, 1)
        nup_row.addWidget(QLabel("Grid"))
        nup_row.addWidget(self.grid_combo, 1)
        layout.addRow("Pages per sheet", nup_row)
        layout.addRow("Paper size", self.paper_edit)
        layout.addRow("Orientation", self.orientation_combo)
        layout.addRow("Page range", self.pages_edit)
        layout.addRow(self.fit_check)
        layout.addRow(advanced_toggle)
        layout.addRow(advanced_box)

        self.load_settings(default_print_settings())

    def _sync_grids(self, per_sheet: int) -> None:
        from ..core.pages import grids_for

        self.grid_combo.clear()
        for cols, rows in grids_for(per_sheet):
            self.grid_combo.addItem(f"{cols} \u00d7 {rows}", (cols, rows))
        self.grid_combo.setEnabled(per_sheet > 1)

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
            pages_per_sheet=self.nup_spin.value(),
            pages_grid=self.grid_combo.currentData() if self.nup_spin.value() > 1 else None,
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
        self.nup_spin.setValue(settings.pages_per_sheet)
        if settings.pages_grid:
            self.grid_combo.setCurrentIndex(max(0, self.grid_combo.findData(settings.pages_grid)))
