"""The QGraphicsView the Progressão do Mundo node graph renders into.
Trimmed copy of items/skill_tree/view.py's _TreeView — no stats overlay
(Progressão has no aggregate panel), same wheel-zoom / Delete / Ctrl+Z
wiring and self-healing mousePressEvent/mouseReleaseEvent for a connect or
redirect drag whose release never reached the item it started on.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QKeySequence


class _ProgressionView(QGraphicsView):
    def __init__(self, canvas: "ProgressionCanvas"):
        super().__init__(canvas._scene)
        self._canvas = canvas
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._canvas.zoom_by(factor)

    def mousePressEvent(self, event):
        if self._canvas._connecting_from is not None:
            self._canvas._finish_connect(self.mapToScene(event.pos()))
        elif self._canvas._redirecting_edge is not None:
            self._canvas._finish_redirect(self.mapToScene(event.pos()))
        elif self.itemAt(event.pos()) is None:
            # Clicking empty canvas space doesn't hit any _ProgressionNode's
            # own mousePressEvent (see items.py), so without this a card
            # selected earlier (blue ACCENT border, see _ProgressionNode.
            # paint) stayed marked "_selected" forever — even after editing
            # its actual color, since that flag is never QGraphicsItem's own
            # isSelected(), just a bool this canvas tracks by hand.
            self._canvas._select_node(None)
        self.setFocus()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
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
