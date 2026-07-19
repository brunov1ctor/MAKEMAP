"""ZoneVisual — thin wrapper around a painted Região zone's scene item(s)."""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsSimpleTextItem


def star_text(stars: int) -> str:
    stars = max(0, min(5, stars))
    return "★" * stars + "☆" * (5 - stars)


class ZoneVisual:
    """root_item is the translucent fill; name/stars are its children (so
    they move, hide, and delete together with it automatically)."""

    def __init__(self, root_item: QGraphicsPathItem,
                 name_item: QGraphicsSimpleTextItem,
                 stars_item: QGraphicsSimpleTextItem):
        self.root_item = root_item
        self._name_item = name_item
        self._stars_item = stars_item

    def set_name(self, name: str):
        self._name_item.setText(name)
        self.recenter(self.root_item.path().boundingRect().center())

    def set_stars(self, stars: int):
        self._stars_item.setText(star_text(stars))
        self.recenter(self.root_item.path().boundingRect().center())

    def set_visible(self, visible: bool):
        self.root_item.setVisible(visible)

    def recenter(self, center: QPointF):
        name_rect = self._name_item.boundingRect()
        self._name_item.setPos(center.x() - name_rect.width() / 2, center.y() - name_rect.height())
        stars_rect = self._stars_item.boundingRect()
        self._stars_item.setPos(center.x() - stars_rect.width() / 2, center.y())
