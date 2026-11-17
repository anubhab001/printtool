"""Reusable settings editor widget: used both as the "global settings" panel
and inside the per-file override dialog, so the two never drift apart.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
        for d in Duplex:
            self.duplex_combo.addItem(d.value.replace("_", " ").title(), d)

        self.paper_edit = QLineEdit()
        self.paper_edit.setPlaceholderText("e.g. A4, Letter (blank = printer default)")

        self.orientation_combo = QComboBox()
        orientation_labels = {Orientation.AUTO: "Automatic"}
        for o in Orientation:
            self.orientation_combo.addItem(orientation_labels.get(o, o.value.title()), o)

        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText('e.g. 1-3,5 (blank = all pages)')

        self.fit_check = QCheckBox("Fit to page")
        self.fit_check.setChecked(True)

        self.collate_check = QCheckBox("Collate")
        self.collate_check.setChecked(True)

        self.buffer_copy_check = QCheckBox("Copy to a temporary file before printing")
        self.buffer_copy_check.setToolTip(
            "Protects against removable media (e.g. a USB drive) being pulled mid-job."
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
        layout.addRow("Copies", self.copies_spin)
        layout.addRow("Duplex", self.duplex_combo)
        layout.addRow("Paper size", self.paper_edit)
        layout.addRow("Orientation", self.orientation_combo)
        layout.addRow("Page range", self.pages_edit)
        layout.addRow(self.fit_check)
        layout.addRow(self.collate_check)
        layout.addRow(advanced_toggle)
        layout.addRow(advanced_box)

        self.load_settings(default_print_settings())

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
            collate=self.collate_check.isChecked(),
            buffer_copy=self.buffer_copy_check.isChecked(),
            delete_after_print=self.delete_after_print_check.isChecked(),
            mirror_lr=self.mirror_lr_check.isChecked(),
            mirror_tb=self.mirror_tb_check.isChecked(),
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
        self.collate_check.setChecked(settings.collate)
        self.buffer_copy_check.setChecked(settings.buffer_copy)
        self.delete_after_print_check.setChecked(settings.delete_after_print)
        self.mirror_lr_check.setChecked(settings.mirror_lr)
        self.mirror_tb_check.setChecked(settings.mirror_tb)
