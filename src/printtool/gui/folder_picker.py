"""Recursive folder picker: shows every printable file under a folder
(including subfolders) as a checkable tree, so individual files or whole
subfolders can be deselected before they are added to the queue.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QDialog

from ..core.discovery import find_printable_files
from ..core.settings import load_extensions

PATH_ROLE = Qt.UserRole


class FolderPickerDialog(QDialog):
    def __init__(self, folder: Path, parent=None, *, advanced: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Files in {folder.name or folder}")
        self.resize(480, 500)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(self._on_item_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tree)
        layout.addWidget(buttons)

        self._folder_items: dict[Path, QTreeWidgetItem] = {}
        self._populate(folder, advanced)

    def _populate(self, folder: Path, advanced: bool) -> None:
        base_extensions = load_extensions(advanced=False)
        extensions = load_extensions(advanced=advanced)
        files = find_printable_files(folder, extensions, recursive=True)
        # The root folder itself gets no tree item/checkbox; its direct
        # children attach straight to the tree's invisible root.
        self._folder_items[folder] = None

        for path in files:
            parent_item = self._folder_item_for(path.parent, folder)
            file_item = QTreeWidgetItem(parent_item, [path.name])
            file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
            # An advanced-only format (not in printable_extensions) starts
            # unchecked, so turning on "advanced" never silently queues a
            # format the user has not actively opted into for this folder.
            is_base = path.suffix.lower().lstrip(".") in base_extensions
            file_item.setCheckState(0, Qt.Checked if is_base else Qt.Unchecked)
            file_item.setData(0, PATH_ROLE, path)

        self.tree.expandAll()

    def _folder_item_for(self, folder: Path, root: Path) -> QTreeWidget | QTreeWidgetItem:
        if folder in self._folder_items and self._folder_items[folder] is not None:
            return self._folder_items[folder]

        if folder == root:
            return self.tree

        parent_item = self._folder_item_for(folder.parent, root)
        item = QTreeWidgetItem(parent_item, [folder.name])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
        item.setCheckState(0, Qt.Checked)
        self._folder_items[folder] = item
        return item

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if item.data(0, PATH_ROLE) is not None:
            return
        state = item.checkState(column)
        if state == Qt.PartiallyChecked:
            return
        self.tree.blockSignals(True)
        self._set_subtree_checked(item, state)
        self.tree.blockSignals(False)

    def _set_subtree_checked(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_subtree_checked(child, state)

    def selected_files(self) -> list[Path]:
        selected: list[Path] = []

        def walk(item) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                path = child.data(0, PATH_ROLE)
                if path is not None:
                    if child.checkState(0) == Qt.Checked:
                        selected.append(path)
                else:
                    walk(child)

        walk(self.tree.invisibleRootItem())
        return selected
