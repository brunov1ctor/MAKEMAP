"""The QGraphicsView the node graph renders into, plus the floating stats
overlay anchor (see set_stats_overlay). Duck-types its `canvas` back-
reference the same way items.py does, so it needs no import of
SkillTreeCanvas or _TreeStatsPanel — the overlay's own type only shows up
in (string, thanks to `from __future__ import annotations`) type hints.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter


class _TreeView(QGraphicsView):
    """QGraphicsView with wheel-zoom and a Delete key that removes whatever
    connection is currently selected (nodes are dragged/connected directly
    via _NodeItem, not from here)."""

    def __init__(self, canvas: "SkillTreeCanvas"):
        super().__init__(canvas._scene)
        self._canvas = canvas
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._stats_overlay: "_TreeStatsPanel | None" = None

    def set_stats_overlay(self, panel: "_TreeStatsPanel"):
        """Floats the stats panel directly over the canvas viewport (bottom-
        right corner) instead of reserving a real layout column beside it —
        the node graph keeps the full view width, the panel just sits on
        top of it, sized to its own content (see _TreeStatsPanel)."""
        panel.setParent(self.viewport())
        panel._owner_view = self
        self._stats_overlay = panel
        panel.adjustSize()
        self._reposition_stats_overlay()
        panel.raise_()

    def _reposition_stats_overlay(self):
        if self._stats_overlay is None:
            return
        pad = 8
        panel = self._stats_overlay
        panel.move(self.viewport().width() - panel.width() - pad,
                   self.viewport().height() - panel.height() - pad)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_stats_overlay()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._canvas.zoom_by(factor)

    def mousePressEvent(self, event):
        # Self-heals a stuck connect-preview from a previous drag whose
        # release never reached the node (e.g. released outside the
        # window) — the very next click anywhere in the canvas clears it
        # instead of leaving the ghost line stranded indefinitely.
        if self._canvas._connecting_from is not None:
            self._canvas._finish_connect(self.mapToScene(event.pos()))
        self.setFocus()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Safety net: the node's own mouseReleaseEvent normally clears
        # _connecting_from already — this only fires if that release got
        # lost somewhere (e.g. the drag left the OS window before letting
        # go of the button), so the temp arrow doesn't linger as a ghost.
        if self._canvas._connecting_from is not None:
            self._canvas._finish_connect(self.mapToScene(event.pos()))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._canvas._delete_selected_edges()
            return
        super().keyPressEvent(event)
