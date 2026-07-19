"""FlowLayout — arranges items left-to-right, wrapping to next line."""

from PySide6.QtWidgets import QLayout
from PySide6.QtCore import QSize, QRect, QPoint


class FlowLayout(QLayout):
    """Layout that arranges items left-to-right, wrapping to next line."""

    def __init__(self, parent=None, spacing=4):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        content_w = max(0, width - margins.left() - margins.right())
        h = self._do_layout(QRect(0, 0, content_w, 0), test_only=True)
        return h + margins.top() + margins.bottom()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect.marginsRemoved(self.contentsMargins()))

    def sizeHint(self):
        w = self.geometry().width() or 280
        margins = self.contentsMargins()
        content_w = max(0, w - margins.left() - margins.right())
        h = self._do_layout(QRect(0, 0, content_w, 0), test_only=True)
        return QSize(w, h + margins.top() + margins.bottom())

    def minimumSize(self):
        return self.sizeHint()

    def _do_layout(self, rect, test_only=False):
        x = rect.x()
        y = rect.y()
        row_h = 0

        for item in self._items:
            widget = item.widget()
            if widget and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            if x + item_size.width() > rect.right() and row_h > 0:
                x = rect.x()
                y += row_h + self._spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x += item_size.width() + self._spacing
            row_h = max(row_h, item_size.height())

        return y + row_h - rect.y()
