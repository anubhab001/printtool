"""File types dialog: tick which extensions count as printable. Writes printable_extensions in settings.yaml, which stays the hand-editable source of truth."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QLabel, QPushButton, QVBoxLayout

from ..core import settings

PRESETS = ["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "odt", "rtf", "txt", "html", "png", "jpg"]


class FileTypesDialog(QDialog):
    def __init__(self, open_settings_file, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Printable formats")
        current = set(settings.load_defaults()["printable_extensions"])
        self._boxes: dict[str, QCheckBox] = {}

        grid = QGridLayout()
        for i, ext in enumerate(sorted(set(PRESETS) | current, key=lambda e: (e not in PRESETS, e))):
            box = QCheckBox(ext.upper())
            box.setChecked(ext in current)
            self._boxes[ext] = box
            grid.addWidget(box, i // 4, i % 4)

        note = QLabel("Formats other than PDF print only if the system print backend supports them.")
        note.setWordWrap(True)
        edit_yaml = QPushButton("Edit settings.yaml...")
        edit_yaml.clicked.connect(lambda: (open_settings_file(), self.reject()))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(note)
        layout.addWidget(edit_yaml)
        layout.addWidget(buttons)

    def _save(self) -> None:
        chosen = [ext for ext, box in self._boxes.items() if box.isChecked()]
        settings.save_defaults({"printable_extensions": chosen or ["pdf"]})
        self.accept()
