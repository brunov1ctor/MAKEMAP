"""ProgressionMediator — owns everything specific to the Progressão do
Mundo panel: wiring its ProgressionRepository once a project is open, the
"pick a point on the map" flow behind each card's 📍 button (arms
PickPointTool, restores whatever tool was active before, then writes the
picked point back onto the card and centers/pings the map when a pin is
clicked afterward), and mirroring every pipeline's pins/connections onto
the real map via ProgressionMapOverlay (see map_overlay.py) so the route
reads directly on the map, not just inside the panel's own mini graph.
Self-contained, mirrors MarkerMediator's style.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, QPointF
from PySide6.QtWidgets import QGraphicsEllipseItem
from PySide6.QtGui import QColor, QPen

from src.canvas.tools.pick_point_tool import PickPointTool
from src.canvas.z_order import ZOrder
from src.layouts.panels.progression.map_overlay import ProgressionMapOverlay

if TYPE_CHECKING:
    from src.layouts.main_layout import MainLayout

logger = logging.getLogger("MAKEMAP")

_PING_MS = 1400


class ProgressionMediator:
    def __init__(self, layout: MainLayout):
        self._l = layout
        self._uow = None
        self._pick_tool = PickPointTool(self._l.canvas.engine.viewport)
        self._l.canvas.engine.tool_manager.register(self._pick_tool)
        self._pick_tool.point_picked.connect(self._on_point_picked)
        self._pick_tool.cancelled.connect(self._on_pick_cancelled)
        self._l.canvas.engine.tool_changed.connect(self._on_tool_changed)
        self._picking_canvas = None
        self._picking_node = None
        self._previous_tool = ""

        self._ping_item: QGraphicsEllipseItem | None = None
        self._ping_timer = QTimer()
        self._ping_timer.setSingleShot(True)
        self._ping_timer.timeout.connect(self._clear_ping)

        self._map_overlay = ProgressionMapOverlay(
            scene_provider=lambda: self._l.canvas.engine.viewport.scene())

        self._l.progression.pin_pick_requested.connect(self._on_pin_pick_requested)
        self._l.progression.pin_locate_requested.connect(self._on_pin_locate_requested)
        self._l.progression.pipeline_created.connect(self._on_pipeline_created)

    # ─── Persistência ───

    def set_uow(self, uow):
        self._uow = uow
        self._l.progression.set_repo(uow.progression if uow else None)

    # ─── Espelhar pinos/conexões no mapa real ───

    def _on_pipeline_created(self, canvas):
        canvas.changed.connect(self._refresh_map_overlay)

    def _refresh_map_overlay(self):
        pipelines = [
            {"nodes": pipe["canvas"].nodes(), "edges": pipe["canvas"]._edges}
            for pipe in self._l.progression._pipelines
        ]
        self._map_overlay.rebuild(
            pipelines, on_marker_moved=self._on_marker_dragged,
            on_marker_remove=self._on_marker_remove_requested,
        )
        # These items are tagged item_type "marker" (see map_overlay.py) so
        # they ride the same "Marcadores" entry in Camadas Ativas as a real
        # placed MarkerItem — but rebuild() tears down and recreates every
        # item, so if the user had that layer hidden it must be re-hidden
        # here, or it'd silently pop back to visible on the next change.
        layers = getattr(self._l, "layers_panel", None)
        if layers is not None:
            layers.refresh()
            if "Marcadores" in layers._hidden:
                for item in self._map_overlay.items():
                    item.setVisible(False)

    def _on_marker_dragged(self, node, scene_pos: QPointF):
        """The map marker itself was dragged to a new spot (see
        _MapMarkerItem.moved) — write it back onto the card's pin. Goes
        through the card's own canvas so this persists and rebuilds the
        overlay exactly like picking a fresh point would."""
        node._canvas.set_node_pin(node, scene_pos.x(), scene_pos.y())

    def _on_marker_remove_requested(self, node):
        """The map marker's ✕ badge was clicked (see _MapMarkerItem.
        remove_requested) — same path as right-clicking the pin button on
        the card itself (see items.py's pin_clear_requested), so it's
        handled the same way: canvas._on_pin_clear() clears the pin and
        persists, which then drops this marker on the next rebuild()."""
        node.pin_clear_requested.emit(node)

    # ─── Marcar no mapa (📍) ───

    def _on_pin_pick_requested(self, payload):
        canvas, node = payload
        self._picking_canvas = canvas
        self._picking_node = node
        self._previous_tool = self._l.canvas.engine.tool_manager.active_name
        self._l.canvas.engine.tool_manager.activate(self._pick_tool.name)

    def _on_point_picked(self, scene_pos: QPointF):
        canvas, node = self._picking_canvas, self._picking_node
        self._picking_canvas = None
        self._picking_node = None
        if canvas is not None and node is not None:
            canvas.set_node_pin(node, scene_pos.x(), scene_pos.y())
        if self._previous_tool:
            self._l.canvas.engine.tool_manager.activate(self._previous_tool)
            self._previous_tool = ""

    def _on_pick_cancelled(self):
        """Escape while picking (see PickPointTool.key_press) — same
        cleanup as a successful pick, minus writing the pin."""
        self._picking_canvas = None
        self._picking_node = None
        if self._previous_tool:
            self._l.canvas.engine.tool_manager.activate(self._previous_tool)
            self._previous_tool = ""

    def _on_tool_changed(self, name: str):
        """The user can also abandon a pick by clicking a different tool on
        the toolbar directly, bypassing both point_picked and cancelled —
        without this, _picking_canvas/_picking_node/_previous_tool would be
        left stale and the next 📍 click would silently reuse them."""
        if self._picking_canvas is None and self._picking_node is None:
            return
        if name == self._pick_tool.name:
            return
        self._picking_canvas = None
        self._picking_node = None
        self._previous_tool = ""

    # ─── Ver no mapa (🎯) ───

    def _on_pin_locate_requested(self, payload):
        _canvas, node = payload
        if not node.pin:
            return
        scene_pos = QPointF(node.pin["x"], node.pin["y"])
        self._l.canvas.engine.viewport.center_on_point(scene_pos)
        self._show_ping(scene_pos, QColor(node.color))

    def _show_ping(self, center: QPointF, color: QColor):
        self._clear_ping()
        scene = self._l.canvas.engine.viewport.scene()
        if scene is None:
            return
        radius = 26
        ring = QGraphicsEllipseItem(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        ring.setPen(QPen(color, 4))
        ring.setZValue(ZOrder.CURSOR_GHOST)
        scene.addItem(ring)
        self._ping_item = ring
        self._ping_timer.start(_PING_MS)

    def _clear_ping(self):
        if self._ping_item is None:
            return
        try:
            scene = self._ping_item.scene()
            if scene is not None:
                scene.removeItem(self._ping_item)
        except RuntimeError:
            pass
        self._ping_item = None
