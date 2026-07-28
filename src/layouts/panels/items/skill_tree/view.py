"""The QGraphicsView the node graph renders into, plus the floating stats
overlay anchor (see set_stats_overlay). Duck-types its `canvas` back-
reference the same way items.py does, so it needs no import of
SkillTreeCanvas or _TreeStatsPanel — the overlay's own type only shows up
in (string, thanks to `from __future__ import annotations`) type hints.
"""

from __future__ import annotations

import math

from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPainter, QKeySequence


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
        # Belt-and-suspenders alongside resizeEvent below: during a live
        # QSplitter drag (see items/panel.py's _skills_splitter), Qt can
        # relayout QAbstractScrollArea's viewport (this._view's own
        # viewport() widget) without necessarily routing back through this
        # QGraphicsView's own resizeEvent on every intermediate frame — the
        # overlay would visibly lag a step behind the border while dragging.
        # Watching the viewport's own QEvent.Resize directly closes that gap.
        self.viewport().installEventFilter(self)

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

    # Viewport size at which the overlay renders at its 1.0 baseline scale
    # (see _MiniRadar/_TreeStatsPanel.set_scale) — below this it shrinks
    # down to MIN_STATS_SCALE, above it grows up to MAX_STATS_SCALE, so
    # resizing the tree column noticeably changes the overlay's own size
    # instead of it staying a fixed pixel box that reads as permanently
    # "compressed" once the rest of the panel has grown around it.
    STATS_SCALE_BASELINE_W = 500
    STATS_SCALE_BASELINE_H = 420
    MIN_STATS_SCALE = 0.8
    MAX_STATS_SCALE = 1.8

    def _stats_scale(self) -> float:
        vp = self.viewport()
        width_ratio = vp.width() / self.STATS_SCALE_BASELINE_W
        height_ratio = vp.height() / self.STATS_SCALE_BASELINE_H
        # Geometric mean, not min() — the tree column is usually wide but
        # short, so height_ratio was almost always the smaller of the two,
        # and min() picked it every time. That made dragging the column
        # *wider* a no-op for the overlay's size (only height_ratio moved
        # the number), which read as the overlay being stuck. The mean lets
        # either dimension grow the scale; the vp.height()/140 term below
        # still caps it so a short-but-very-wide column can't inflate the
        # overlay past what its own height can actually hold.
        factor = math.sqrt(width_ratio * height_ratio)
        factor = min(factor, vp.height() / 140)
        return max(self.MIN_STATS_SCALE, min(self.MAX_STATS_SCALE, factor))

    def _reposition_stats_overlay(self):
        if self._stats_overlay is None:
            return
        panel = self._stats_overlay
        panel.set_scale(self._stats_scale())
        pad = 8
        panel.move(self.viewport().width() - panel.width() - pad,
                   self.viewport().height() - panel.height() - pad)
        # Re-asserted on every reposition, not just at setup — a live
        # splitter drag repaints/relayouts the viewport constantly, and the
        # overlay silently falling behind a freshly-repainted sibling would
        # look exactly like "stopped following" even though its position
        # was actually still being updated correctly underneath.
        panel.raise_()

    def eventFilter(self, obj, event):
        if obj is self.viewport() and event.type() == QEvent.Type.Resize:
            self._reposition_stats_overlay()
        return super().eventFilter(obj, event)

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
        elif self._canvas._redirecting_edge is not None:
            self._canvas._finish_redirect(self.mapToScene(event.pos()))
        self.setFocus()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # Safety net: the node's/edge's own mouseReleaseEvent normally
        # clears _connecting_from/_redirecting_edge already — this only
        # fires if that release got lost somewhere (e.g. the drag left the
        # OS window before letting go of the button), so the temp arrow
        # doesn't linger as a ghost.
        if self._canvas._connecting_from is not None:
            self._canvas._finish_connect(self.mapToScene(event.pos()))
        elif self._canvas._redirecting_edge is not None:
            self._canvas._finish_redirect(self.mapToScene(event.pos()))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_edges = [e for e in self._canvas._edges if e.isSelected()]
            if selected_edges:
                self._canvas._delete_selected_edges()
            elif self._canvas._selected_node is not None:
                self._canvas._delete_node(self._canvas._selected_node)
            return
        if event.matches(QKeySequence.StandardKey.Undo):
            self._canvas._history.undo()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self._canvas._history.redo()
            return
        super().keyPressEvent(event)
