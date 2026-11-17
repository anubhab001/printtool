"""Exercises the actual internal-drag reorder code path with a minimal
fake QDropEvent, since Qt's native drag-and-drop loop does not run
under the offscreen platform used for headless testing (this is a
known Qt limitation, not specific to this project).
"""

import sys

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from printtool.gui.queue_list import JOB_ID_ROLE, QueueList


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv)


class _FakeDropEvent:
    def __init__(self, source, pos: QPoint):
        self._source = source
        self._pos = pos

    def source(self):
        return self._source

    def position(self):
        return self

    def toPoint(self):  # noqa: N802 - mimics QPointF.toPoint()
        return self._pos

    def acceptProposedAction(self):
        pass


def _populate(queue_list: QueueList, names: list[str]) -> None:
    for name in names:
        item = QtWidgets.QListWidgetItem(name)
        item.setData(JOB_ID_ROLE, name)
        queue_list.addItem(item)


def _names(queue_list: QueueList) -> list[str]:
    return [queue_list.item(i).data(JOB_ID_ROLE) for i in range(queue_list.count())]


def test_drag_reorder_moves_single_item_down(app):
    q = QueueList()
    q.resize(200, 400)
    _populate(q, ["a", "b", "c", "d"])

    q.item(0).setSelected(True)  # drag "a"
    # The lower half of an item means "insert after it"; the upper half
    # (or exactly its center) means "insert before it" -- see _row_at.
    rect = q.visualItemRect(q.item(2))
    drop_point = QPoint(rect.center().x(), rect.bottom() - 1)  # lower half of "c"
    q._reorder_dropped_selection(_FakeDropEvent(source=q, pos=drop_point))

    assert _names(q) == ["b", "c", "a", "d"]


def test_drag_reorder_onto_item_center_inserts_before_it(app):
    q = QueueList()
    q.resize(200, 400)
    _populate(q, ["a", "b", "c", "d"])

    q.item(0).setSelected(True)  # drag "a"
    drop_point = q.visualItemRect(q.item(2)).center()  # exactly on "c"
    q._reorder_dropped_selection(_FakeDropEvent(source=q, pos=drop_point))

    assert _names(q) == ["b", "a", "c", "d"]


def test_drag_reorder_moves_multiple_contiguous_items(app):
    q = QueueList()
    q.resize(200, 400)
    _populate(q, ["a", "b", "c", "d", "e"])

    q.item(0).setSelected(True)
    q.item(1).setSelected(True)  # drag "a" and "b" together
    drop_point = q.visualItemRect(q.item(3)).center()  # drop onto "d"
    q._reorder_dropped_selection(_FakeDropEvent(source=q, pos=drop_point))

    assert _names(q) == ["c", "a", "b", "d", "e"]


def test_drag_reorder_to_end_of_list(app):
    q = QueueList()
    q.resize(200, 400)
    _populate(q, ["a", "b", "c"])

    q.item(0).setSelected(True)
    below_last = q.visualItemRect(q.item(2)).bottomLeft() + QPoint(0, 5)
    q._reorder_dropped_selection(_FakeDropEvent(source=q, pos=below_last))

    assert _names(q) == ["b", "c", "a"]
