"""The print queue widget: a list that accepts files dragged in from the
OS (add), removes an item dragged out to the remove zone or out of the
window entirely (exclude), and reorders by dragging within itself.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QFont
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListWidget, QStyledItemDelegate

JOB_ID_ROLE = Qt.UserRole
STATUS_GLYPH_ROLE = Qt.UserRole + 1
# A zip's header row and every row (nested header or leaf) tracked under
# it share a pointer to that header row via ZIP_GROUP_HEADER_ROLE, so the
# whole block can be moved or removed as one unit; ZIP_GROUP_ROLE marks
# the header row itself.
ZIP_GROUP_ROLE = Qt.UserRole + 2
ZIP_GROUP_HEADER_ROLE = Qt.UserRole + 3

# A plain QListWidgetItem only has one icon slot, already used for the
# file-type icon (left, native). The job status is drawn separately, as
# a right-aligned glyph, by StatusGlyphDelegate below.
STATUS_GLYPHS = {
    # Plain BMP symbols only: the obvious hourglass/flag emoji need a
    # colour-emoji font fallback that is not guaranteed to be installed,
    # and render as a tofu box without it. pending/printing/done read as
    # one circle filling in: empty, half, full.
    "pending": ("○", "#999"),  # empty circle: waiting
    "printing": ("◐", "#2a82da"),  # half-filled circle: in progress
    "done": ("●", "#2a8a2a"),  # filled circle
    "failed": ("✖", "#c0392b"),  # cross
    "cancelled": ("⊘", "#888"),  # circled slash
}


class StatusGlyphDelegate(QStyledItemDelegate):
    """Paints the normal row (the file-type icon plus the filename), then
    a status glyph pinned to the right edge, so a queued file's icon and
    its print status read as two separate things rather than one icon
    standing in for both."""

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        glyph_info = index.data(STATUS_GLYPH_ROLE)
        if not glyph_info:
            return
        glyph, color = glyph_info
        painter.save()
        font = QFont(option.font)
        font.setPointSize(font.pointSize() + 2)
        painter.setFont(font)
        painter.setPen(QColor(color))
        rect = QRectF(option.rect)
        rect.setLeft(rect.right() - 28)
        painter.drawText(rect, int(Qt.AlignVCenter | Qt.AlignRight), glyph)
        painter.restore()


class QueueList(QListWidget):
    files_dropped = Signal(list)  # list[Path], dragged in from outside
    files_dragged_out = Signal(list)  # list[str], dragged out and dropped nowhere
    reordered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)

    def startDrag(self, supportedActions) -> None:  # noqa: N802 - Qt override
        items = self.selectedItems()
        if not items:
            return

        # An empty QMimeData means a real OS drop target (another app, a
        # file manager folder) has nothing to accept, so it also reports
        # Qt.IgnoreAction -- but so does dropping on some other widget of
        # this same window (a button, the settings panel, ...) that just
        # does not implement drag acceptance, which is not a request to
        # remove anything. Only treat it as "dropped outside" when the
        # cursor actually ends up outside this window; the remove zone's
        # own drop target still removes via its own signal, unaffected.
        drag = QDrag(self)
        drag.setMimeData(QMimeData())
        result = drag.exec(Qt.MoveAction)

        if result == Qt.IgnoreAction and not self.window().frameGeometry().contains(QCursor.pos()):
            paths = [item.data(JOB_ID_ROLE) for item in items]
            for item in items:
                self.takeItem(self.row(item))
            self.files_dragged_out.emit(paths)

    def path_at_row(self, row: int) -> str | None:
        item = self.item(row)
        return item.data(JOB_ID_ROLE) if item else None

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.source() is self or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.source() is self:
            self._reorder_dropped_selection(event)
            event.acceptProposedAction()
            self.reordered.emit()
            return

        if event.mimeData().hasUrls():
            paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return

        event.ignore()

    def _row_at(self, pos) -> int:
        item = self.itemAt(pos)
        if item is None:
            return self.count()
        row = self.row(item)
        if pos.y() > self.visualItemRect(item).center().y():
            row += 1
        return row

    def _reorder_dropped_selection(self, event) -> None:
        drop_row = self._row_at(event.position().toPoint())
        selected_rows = sorted(index.row() for index in self.selectedIndexes())
        if not selected_rows:
            return

        items = [self.takeItem(r) for r in reversed(selected_rows)]
        items.reverse()

        removed_above = sum(1 for r in selected_rows if r < drop_row)
        insert_at = drop_row - removed_above

        for offset, item in enumerate(items):
            self.insertItem(insert_at + offset, item)
            item.setSelected(True)


class RemoveDropZone(QLabel):
    """A small, explicit "drag here to remove" target, kept alongside
    QueueList's own drag-out-of-the-window removal (startDrag) as a more
    discoverable alternative for the same action."""

    remove_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Drag a queued file here or outside to remove it", parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 1px dashed gray; padding: 6px; color: gray;")

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.source() is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.acceptProposedAction()
        self.remove_requested.emit()
