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
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        # Without invalidate() here, Qt can keep using cached geometry from
        # before the removal — widgets added right after (e.g. rebuilding a
        # tag list) may sit at stale/default geometry instead of getting
        # laid out, since nothing else marks the layout dirty on removal.
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            self.invalidate()
            return item
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
        # Two passes instead of one: items are first grouped into rows (same
        # left-to-right wrapping as before) to find each row's tallest
        # sizeHint(), THEN placed using that shared row height instead of
        # each item's own — otherwise items whose sizeHint() height varies
        # (e.g. a card whose label wraps to 1 vs 2 lines) end up with
        # mismatched bottoms within the same row, since a single pass places
        # each item using only its own height, before the row's true max is
        # even known. Width stays each item's own; only height is unified,
        # so a shorter item just gets padded out to match its tallest row
        # neighbor instead of being stretched sideways.
        rows: list[tuple[list, int]] = []
        current_row: list = []
        row_h = 0
        x = rect.x()

        for item in self._items:
            widget = item.widget()
            if widget and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            if x + item_size.width() > rect.right() and current_row:
                rows.append((current_row, row_h))
                current_row = []
                row_h = 0
                x = rect.x()
            current_row.append((item, item_size))
            x += item_size.width() + self._spacing
            row_h = max(row_h, item_size.height())

        if current_row:
            rows.append((current_row, row_h))

        y = rect.y()
        for i, (row_items, row_height) in enumerate(rows):
            x = rect.x()
            for item, item_size in row_items:
                if not test_only:
                    item.setGeometry(QRect(QPoint(x, y), QSize(item_size.width(), row_height)))
                x += item_size.width() + self._spacing
            y += row_height
            if i < len(rows) - 1:
                y += self._spacing

        return (y - rect.y()) if rows else 0
