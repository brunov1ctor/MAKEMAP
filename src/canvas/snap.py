"""Snap Manager — snap to grid, items, guides, and pixels."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from src.canvas.grid import GridManager


class SnapMode:
    NONE = 0
    GRID = 1
    ITEM = 2
    GUIDE = 4
    PIXEL = 8


class SnapManager:
    """Handles snapping logic for canvas items."""

    def __init__(self, grid: GridManager):
        self._grid = grid
        # Off by default — snap's meaning is tied to the grid shape (it fills
        # whichever cell you click, in that shape), so picking a shape with
        # nothing snapped on yet is the least surprising starting point.
        self.enabled = False
        self.mode = SnapMode.GRID
        self.threshold = 8.0  # pixels

    @property
    def grid(self) -> GridManager:
        return self._grid

    def snap(self, pos: QPointF) -> QPointF:
        """Snap a position based on current mode."""
        if not self.enabled:
            return pos

        x, y = pos.x(), pos.y()

        if self.mode & SnapMode.GRID:
            x, y = self._grid.snap_sub(x, y)

        if self.mode & SnapMode.PIXEL:
            x, y = round(x), round(y)

        return QPointF(x, y)

    def set_mode(self, mode: int):
        self.mode = mode

    def toggle(self):
        self.enabled = not self.enabled
