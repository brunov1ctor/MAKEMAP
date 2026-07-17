"""PanelManager — centralizes positioning, visibility and glass style for toolbar panels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtWidgets import QWidget, QScrollArea
from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush


# ─── Glass paint helper (shared style) ───────────────────────────────────────

def paint_glass_panel(widget: QWidget, radius: int = 10):
    """Paint the standard dark-glass background on any panel."""
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = widget.width(), widget.height()
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.fillPath(path, QColor(11, 25, 41, 235))
    grad = QLinearGradient(0, 0, 0, h * 0.15)
    grad.setColorAt(0.0, QColor(255, 255, 255, 10))
    grad.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(grad))
    p.setPen(QPen(QColor(255, 255, 255, 25), 1))
    p.drawPath(path)
    p.end()


# ─── Panel descriptor ────────────────────────────────────────────────────────

@dataclass
class PanelEntry:
    name: str
    widget: QWidget
    fill_height: bool = False           # True = always fill max_height (e.g. Brush)
    on_show: Callable | None = None
    on_hide: Callable | None = None
    exclusive: bool = True
    _registered: bool = field(default=False, init=False, repr=False)


# ─── Manager ─────────────────────────────────────────────────────────────────

class PanelManager:
    """Manages floating toolbar panels: registration, visibility, and layout.

    Usage:
        mgr = PanelManager(parent_widget)
        mgr.register("Brush",   brush_panel,   fixed_height=False)
        mgr.register("Grid",    grid_panel,    fixed_height=True)
        mgr.register("Terrain", terrain_panel, fixed_height=False)

        # In resizeEvent:
        mgr.layout(anchor_x, anchor_y, available_width, available_height)

        # Toggle a panel:
        mgr.toggle("Brush")
        mgr.show("Terrain")
        mgr.hide("Grid")
    """

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._panels: dict[str, PanelEntry] = {}

    # ─── Registration ────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        widget: QWidget,
        *,
        fill_height: bool = False,
        on_show: Callable | None = None,
        on_hide: Callable | None = None,
        exclusive: bool = True,
    ):
        self._panels[name] = PanelEntry(
            name=name, widget=widget, fill_height=fill_height,
            on_show=on_show, on_hide=on_hide, exclusive=exclusive,
        )

    # ─── Visibility ──────────────────────────────────────────────────────

    def show(self, name: str):
        entry = self._panels.get(name)
        if not entry:
            return
        if entry.exclusive:
            for other_name, other in self._panels.items():
                if other_name != name and other.exclusive and other.widget.isVisible():
                    self._do_hide(other)
        entry.widget.show()
        entry.widget.raise_()
        if entry.on_show:
            entry.on_show()

    def hide(self, name: str):
        entry = self._panels.get(name)
        if entry:
            self._do_hide(entry)

    def toggle(self, name: str):
        entry = self._panels.get(name)
        if not entry:
            return
        if entry.widget.isVisible():
            self._do_hide(entry)
        else:
            self.show(name)

    def hide_all(self):
        for entry in self._panels.values():
            if entry.widget.isVisible():
                self._do_hide(entry)

    def is_visible(self, name: str) -> bool:
        entry = self._panels.get(name)
        return entry.widget.isVisible() if entry else False

    def _do_hide(self, entry: PanelEntry):
        entry.widget.hide()
        if entry.on_hide:
            entry.on_hide()

    # ─── Layout ──────────────────────────────────────────────────────────

    def layout(self, x: int, y: int, max_width: int, max_height: int):
        """Reposition all visible panels within the given bounds."""
        for entry in self._panels.values():
            if not entry.widget.isVisible():
                continue
            panel_w = getattr(entry.widget, "PANEL_WIDTH", entry.widget.sizeHint().width())
            panel_w = min(panel_w, max_width)
            if entry.fill_height:
                panel_h = max_height
            else:
                panel_h = min(self._content_height(entry.widget), max_height)
            entry.widget.setGeometry(QRect(x, y, panel_w, panel_h))
            entry.widget.raise_()

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _content_height(widget: QWidget) -> int:
        """Return the natural content height of a panel based on its visible content."""
        scroll = widget.findChild(QScrollArea)
        if scroll and scroll.widget():
            scroll.widget().adjustSize()
            inner = scroll.widget().sizeHint().height()
            margins = scroll.widget().layout().contentsMargins() if scroll.widget().layout() else None
            extra = (margins.top() + margins.bottom()) if margins else 0
            return inner + extra + 20
        widget.adjustSize()
        return widget.sizeHint().height()
