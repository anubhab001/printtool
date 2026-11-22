"""Printable formats: A preset list to tick, and formats of one's own added or removed; kept as printable_extensions (and custom_extensions) in the settings."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..core import settings

PRESETS = ["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "odt", "rtf", "txt", "html", "png", "jpg"]


class FileTypesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Printable formats")
        saved = settings.load_defaults()
        self._chosen = set(saved["printable_extensions"])
        self._custom = [e for e in dict.fromkeys(list(saved.get("custom_extensions") or []) + sorted(self._chosen)) if e not in PRESETS]
        self._boxes: dict[str, QCheckBox] = {}

        self._grid = QGridLayout()
        self._own = QVBoxLayout()
        self._fill()

        self._new = QLineEdit()
        self._new.setPlaceholderText("Extension, e.g. svg")
        self._new.returnPressed.connect(self._add)
        add = QPushButton("Add")
        add.clicked.connect(self._add)
        add_row = QHBoxLayout()
        add_row.addWidget(self._new, 1)
        add_row.addWidget(add)

        note = QLabel("Formats other than PDF print only if the system print backend supports them.")
        note.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Preset"))
        layout.addLayout(self._grid)
        layout.addWidget(QLabel("Own"))
        layout.addLayout(self._own)
        layout.addLayout(add_row)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _fill(self) -> None:
        """The preset formats in a grid; one's own below, each with Remove."""
        for box in self._boxes.values():
            self._chosen.discard(box.text().lower()) if not box.isChecked() else self._chosen.add(box.text().lower())
        for lay in (self._grid, self._own):
            while lay.count():
                w = lay.takeAt(0).widget()
                if w is not None:
                    w.deleteLater()
        self._boxes = {}
        for i, ext in enumerate(PRESETS):
            box = QCheckBox(ext.upper())
            box.setChecked(ext in self._chosen)
            self._boxes[ext] = box
            self._grid.addWidget(box, i // 4, i % 4)
        for ext in self._custom:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            box = QCheckBox(ext.upper())
            box.setChecked(ext in self._chosen)
            self._boxes[ext] = box
            gone = QPushButton("Remove")
            gone.clicked.connect(lambda _c=False, e=ext: self._remove(e))
            line.addWidget(box, 1)
            line.addWidget(gone)
            self._own.addWidget(row)

    def _add(self) -> None:
        ext = self._new.text().strip().lstrip(".").lower()
        self._new.clear()
        if not ext or not ext.isalnum() or ext in PRESETS or ext in self._custom:
            return
        self._custom.append(ext)
        self._chosen.add(ext)
        self._fill()

    def _remove(self, ext: str) -> None:
        self._custom = [e for e in self._custom if e != ext]
        self._chosen.discard(ext)
        self._boxes.pop(ext, None)
        self._fill()

    def _save(self) -> None:
        chosen = [ext for ext, box in self._boxes.items() if box.isChecked()]
        settings.save_defaults({"printable_extensions": chosen or ["pdf"], "custom_extensions": self._custom})
        self.accept()
