"""The print queue widget: a list that accepts files dragged in from the
OS (add), removes an item dragged out to the remove zone or out of the
window entirely (exclude), and reorders by dragging within itself.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QListWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

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

    INDENT = "\u2003\u2003"
    STEP = 22  # pixels per nesting level

    @classmethod
    def _depth(cls, text: str) -> int:
        return (len(text) - len(text.lstrip(cls.INDENT[0]))) // len(cls.INDENT)

    def _tree_lines(self, painter, option, index, depth: int) -> None:
        """Grey connector lines with a rounded elbow, drawn in the gutter the
        row was shifted by, like a file tree."""
        model = index.model()
        texts = [model.index(r, 0).data() or "" for r in range(index.row() + 1, model.rowCount())]
        later = [self._depth(t) for t in texts]
        rect = option.rect
        mid = rect.center().y()
        x0 = rect.left() + 10
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#a8adb5"), 1.4))
        for level in range(1, depth + 1):
            x = x0 + (level - 1) * self.STEP
            # Does another row at this level follow before the branch closes?
            continues = False
            for d in later:
                if d < level:
                    break
                if d == level:
                    continues = True
                    break
            if level == depth:
                path = QPainterPath()
                path.moveTo(x, rect.top())
                path.lineTo(x, mid - 5)
                path.quadTo(x, mid, x + 5, mid)
                path.lineTo(x + self.STEP - 6, mid)
                painter.drawPath(path)
                if continues:
                    painter.drawLine(int(x), int(mid), int(x), rect.bottom())
            elif continues:
                painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
        painter.restore()

    def paint(self, painter, option, index) -> None:
        depth = self._depth(index.data() or "")
        if depth:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.text = opt.text.lstrip(self.INDENT[0])
            opt.rect = option.rect.adjusted(depth * self.STEP, 0, 0, 0)
            style = opt.widget.style() if opt.widget else QApplication.style()
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
            self._tree_lines(painter, option, index, depth)
            option = opt
        else:
            super().paint(painter, option, index)
        if index.data(Qt.CheckStateRole) in (Qt.PartiallyChecked, Qt.PartiallyChecked.value):
            # Light blue box: only some pages, or only some files of a group.
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            style = opt.widget.style() if opt.widget else QApplication.style()
            box = QRectF(style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, opt, opt.widget)).adjusted(1, 1, -1, -1)
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QColor("#5b9bd5"))
            painter.setBrush(QColor("#a9cff2"))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QPen(QColor("white"), 2))
            mid = box.center().y()
            painter.drawLine(int(box.left() + 4), int(mid), int(box.right() - 4), int(mid))
            painter.restore()
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
    urls_dropped = Signal(list)  # list[str], web links dragged in (a browser, web mail)
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
        # The file's own icon follows the pointer, with the count when several.
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

        pix = QPixmap(40, 40)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.drawPixmap(4, 4, items[0].icon().pixmap(32, 32))
        if len(items) > 1:
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor("#2f6fd6"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(22, 22, 18, 18)
            p.setPen(QColor("white"))
            f = QFont()
            f.setPixelSize(10)
            f.setBold(True)
            p.setFont(f)
            p.drawText(22, 22, 18, 18, Qt.AlignCenter, str(len(items)))
        p.end()
        drag.setPixmap(pix)
        drag.setHotSpot(pix.rect().center())
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
        virtual = 'application/x-qt-windows-mime;value="FileGroupDescriptorW"' in event.mimeData().formats()
        if event.source() is self or event.mimeData().hasUrls() or virtual:
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

        from ..core import fetch

        # An attachment dragged from a mail program: saved from the drag.
        attached = fetch.virtual_files(event.mimeData())
        if attached:
            self.files_dropped.emit(attached)
            event.acceptProposedAction()
            return

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()]
            web = [u.toString() for u in urls if u.scheme() in ("http", "https")]
            if paths:
                self.files_dropped.emit(paths)
            if web:
                self.urls_dropped.emit(web)
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

    _CALM = ("QLabel { background: #fdecef; border: 1px dashed #e3a1ad; border-radius: 6px; padding: 5px; color: #a8495a; }"
             " QLabel:disabled { background: #f6f1f2; border-color: #e2d4d7; color: #c9b5b9; }")
    _HOT = "QLabel { background: #f8c6cf; border: 1px solid #d2556b; border-radius: 6px; padding: 5px; color: #8a2236; }"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

        # A drawn bin, then the word: the bottom of the queue reads as the
        # place things go to be removed.
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#a8495a"), 1.4))
        p.drawLine(2, 4, 14, 4)
        p.drawLine(6, 4, 6, 2)
        p.drawLine(6, 2, 10, 2)
        p.drawLine(10, 2, 10, 4)
        p.drawRect(4, 5, 8, 9)
        p.drawLine(7, 7, 7, 12)
        p.drawLine(9, 7, 9, 12)
        p.end()
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice

        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        pix.save(buf, "PNG")
        icon = "data:image/png;base64," + bytes(data.toBase64()).decode()
        self.setText(f'<img src="{icon}" style="vertical-align: middle"> Remove')
        self.setToolTip("Drag a queued file here, or out of the window, to remove it")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(self._CALM)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.source() is not None and self.isEnabled():
            event.acceptProposedAction()
            self.setStyleSheet(self._HOT)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.setStyleSheet(self._CALM)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.acceptProposedAction()
        self.setStyleSheet(self._CALM)
        self.remove_requested.emit()
