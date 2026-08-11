"""ProgressionMapOverlay — mirrors every pipeline's pinned cards straight
onto the real map: a small, draggable marker at each pin (dragging it
updates that card's pin — see _MapMarkerItem.moved/ProgressionMediator.
_on_marker_dragged), and a flowing neon line between two pins whenever
their cards are connected in the Progressão panel — so the intended route
reads directly on the map itself, at a glance, instead of only inside the
panel's own mini node graph. The connector lines stay purely decorative
(setAcceptedMouseButtons(NoButton)) so they never get in the way of editing
the map underneath them; only the marker itself is interactive.

Owned and driven by ProgressionMediator, which calls rebuild() whenever any
pipeline's graph changes (ProgressionCanvas.changed).
"""

from __future__ import annotations

import math

from PySide6.QtWidgets import QGraphicsObject, QGraphicsPathItem, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QPainterPathStroker, QFont, QPolygonF

from src.canvas.item_utils import enable_hover_glow
from src.canvas.z_order import ZOrder
from src.styles.tokens import Colors

_MARKER_R = 9
_FLOW_TICK_MS = 40
_FLOW_STEP = 0.01
_FLOW_SPAN = 0.06
_HOVER_SCALE = 1.15  # same feel as MarkerItem's own hover (see marker_item.py)
_CLOSE_R = 6
_CLOSE_CENTER = QPointF(_MARKER_R * 0.72, -_MARKER_R * 0.72)


def _arrow_head_polygon(tip: QPointF, angle: float, size: float, spread: float) -> QPolygonF:
    notch_depth = size * 0.45
    right = QPointF(tip.x() - math.cos(angle - spread) * size, tip.y() - math.sin(angle - spread) * size)
    left = QPointF(tip.x() - math.cos(angle + spread) * size, tip.y() - math.sin(angle + spread) * size)
    notch = QPointF(tip.x() - math.cos(angle) * notch_depth, tip.y() - math.sin(angle) * notch_depth)
    return QPolygonF([tip, right, notch, left])


class _MapMarkerItem(QGraphicsObject):
    """A small, draggable pin at a card's map location — sits just under
    real MarkerItems (ZOrder.PLACED_GIZMO, see marker_mediator.py) so an
    actual placed marker always reads on top of this one if they overlap.

    Dragging on this canvas is never Qt's native per-item mouse handling —
    CanvasEngine replaces the viewport's mouse handlers wholesale and
    reimplements object dragging itself (ItemInteraction/TransformEngine),
    gated entirely by the ItemIsSelectable flag (see SelectionEngine.
    is_selectable). Without it, every tool's hit-test simply never finds
    this item — under Pan that was invisible (a drag anywhere pans the
    whole camera, which looks like the marker "followed" the cursor but
    never actually changed its own scene position), under Selecionar it
    was an obvious dead click. Matches how the real MarkerItem (marker_
    item.py) is made draggable — same flag, no mouse-event overrides."""

    moved = Signal(object, QPointF)  # (the _ProgressionNode this pin belongs to, new scene pos)
    remove_requested = Signal(object)  # the _ProgressionNode whose pin should be cleared

    # How long the position must sit still before _on_settled fires and
    # persists it — ItemPositionHasChanged fires on every intermediate
    # step of a drag (TransformEngine.move() calls moveBy() per mouse-move
    # tick), and persisting immediately would rebuild this very item mid-
    # drag on every one of those ticks.
    _SETTLE_MS = 200

    def __init__(self, node, pos: QPointF, color: str, icon: str):
        super().__init__()
        self._node = node
        self.setPos(pos)
        self._color = QColor(color)
        self._icon = icon
        self.setZValue(ZOrder.PROGRESSION_PIN)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setToolTip(f"Arraste para reposicionar o marcador de \"{node.name}\" • ✕ remove do mapa")
        # Tagged as a regular "marker" — rides the same "Marcadores" entry
        # in Camadas Ativas / the Selecionar tool's layer filter as a real
        # placed MarkerItem, instead of needing its own separate category.
        self.setData(0, {"item_type": "marker"})
        self._settle_timer = QTimer()
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._on_settled)
        self._hovered = False
        # Same helper + glow recipe as the real MarkerItem (marker_item.py)
        # so this reads/feels identical on hover to every other object on
        # the map — scale up plus an accent-colored drop shadow.
        enable_hover_glow(self, self._on_hover)

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged:
            self._settle_timer.start(self._SETTLE_MS)
        return super().itemChange(change, value)

    def _on_settled(self):
        self.moved.emit(self._node, self.pos())

    def _on_hover(self, hovered: bool):
        self._hovered = hovered
        if hovered:
            self.setScale(_HOVER_SCALE)
            glow = QGraphicsDropShadowEffect()
            glow.setColor(QColor(Colors.ACCENT))
            glow.setBlurRadius(24)
            glow.setOffset(0, 0)
            self.setGraphicsEffect(glow)
        else:
            self.setScale(1.0)
            self.setGraphicsEffect(None)
            # Otherwise a cursor left ArrowCursor by hoverMoveEvent (below)
            # while leaving over the ✕ badge would stick after the mouse is
            # already off the item entirely, instead of falling back to
            # whatever cursor the active tool/viewport normally shows.
            self.unsetCursor()
        self.update()

    def hoverMoveEvent(self, event):
        # The ✕ badge is a click target, not a drag handle — without this
        # it inherited whatever drag-hint cursor (e.g. Pan's OpenHandCursor)
        # the rest of this draggable marker shows, which read as "you can
        # drag from here" over a spot that actually deletes on click.
        if self._over_close_badge(event.pos()):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def _over_close_badge(self, local_pos: QPointF) -> bool:
        return self._hovered and math.hypot(
            local_pos.x() - _CLOSE_CENTER.x(), local_pos.y() - _CLOSE_CENTER.y()
        ) <= _CLOSE_R

    def boundingRect(self) -> QRectF:
        r = _MARKER_R + 6
        return QRectF(-r, -r, 2 * r, 2 * r)

    def try_close(self, scene_pos: QPointF) -> bool:
        """If `scene_pos` lands on the ✕ badge — only live while hovered,
        matching the badge only being drawn then (see paint()) — emit
        remove_requested and report the click as handled. Duck-typed by
        CanvasEngine._on_mouse_press so it can special-case a click here
        without the generic canvas engine importing this progression-
        specific item class."""
        if not self._over_close_badge(self.mapFromScene(scene_pos)):
            return False
        self.remove_requested.emit(self._node)
        return True

    def set_appearance(self, color: str, icon: str):
        """Update in place instead of the caller throwing this item away
        and making a new one — see ProgressionMapOverlay.rebuild()'s
        docstring for why a rebuild must never swap a live marker's
        identity out from under it."""
        new_color = QColor(color)
        changed = new_color != self._color or icon != self._icon
        self._color = new_color
        self._icon = icon
        if changed:
            self.update()

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QColor(self._color)
        glow.setAlpha(70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(0, 0), _MARKER_R + 4, _MARKER_R + 4)
        p.setPen(QPen(self._color, 2))
        p.setBrush(QBrush(QColor(12, 20, 34, 235)))
        p.drawEllipse(QPointF(0, 0), _MARKER_R, _MARKER_R)
        p.setFont(QFont("Segoe UI Emoji", 8))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(-_MARKER_R, -_MARKER_R, 2 * _MARKER_R, 2 * _MARKER_R),
                   Qt.AlignmentFlag.AlignCenter, self._icon)
        if self._hovered:
            self._paint_close_badge(p)

    def _paint_close_badge(self, p: QPainter):
        danger = QColor(Colors.ERROR)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(danger))
        p.drawEllipse(_CLOSE_CENTER, _CLOSE_R, _CLOSE_R)
        p.setPen(QPen(QColor("#FFFFFF"), 1.4))
        d = _CLOSE_R * 0.45
        cx, cy = _CLOSE_CENTER.x(), _CLOSE_CENTER.y()
        p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
        p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))


class _MapFlowEdgeItem(QGraphicsPathItem):
    """A neon connector between two pinned cards on the real map, with the
    same travelling-light effect as the panel's own _ProgressionEdge (see
    progression/items.py) — the "sequence" cue the map itself was missing.
    Hover-reactive the same way the marker/every other object on the map
    is (brighter line + glow) — not just the marker icon — even though it
    still doesn't accept clicks (setAcceptedMouseButtons(NoButton)), so it
    never gets in the way of editing whatever's underneath it."""

    ARROW_SIZE = 12
    ARROW_SPREAD = math.radians(24)
    LINE_WIDTH = 2.4
    HIT_WIDTH = 14  # invisible hover/click hit-test band around the thin drawn line

    def __init__(self, a: QPointF, b: QPointF, color: str, overlay: "ProgressionMapOverlay"):
        super().__init__()
        self._color = QColor(color)
        self._overlay = overlay
        self._hovering = False
        self.setZValue(ZOrder.PROGRESSION_CONNECTOR)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        # Tagged "marker" too — hides/shows together with the pins it
        # connects under the same "Marcadores" layer entry.
        self.setData(0, {"item_type": "marker"})
        enable_hover_glow(self, self._on_hover)
        # Pulled back from each marker's own center (a/b as given) to just
        # outside its glow ring — the marker sits on top (higher zValue),
        # so a line/arrowhead that reached all the way to the center used
        # to end up hidden underneath the opaque icon instead of visibly
        # pointing at it.
        clearance = _MARKER_R + 6
        dx, dy = b.x() - a.x(), b.y() - a.y()
        dist = math.hypot(dx, dy)
        if dist > clearance * 2:
            ux, uy = dx / dist, dy / dist
            a = QPointF(a.x() + ux * clearance, a.y() + uy * clearance)
            b = QPointF(b.x() - ux * clearance, b.y() - uy * clearance)
        path = QPainterPath(a)
        ctrl = max(abs(b.x() - a.x()) * 0.35, 30)
        path.cubicTo(QPointF(a.x() + ctrl, a.y()), QPointF(b.x() - ctrl, b.y()), b)
        self.setPath(path)

    def boundingRect(self) -> QRectF:
        margin = self.ARROW_SIZE + 10
        return self.path().boundingRect().adjusted(-margin, -margin, margin, margin)

    def shape(self):
        # The drawn stroke is only LINE_WIDTH (~2px) wide — far too thin a
        # target to reliably catch a hover on its own; stroke a much wider
        # invisible band around the same path just for hit-testing (paint()
        # still only draws the thin line).
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        return stroker.createStroke(self.path())

    def _on_hover(self, hovered: bool):
        self._hovering = hovered
        if hovered:
            glow = QGraphicsDropShadowEffect()
            glow.setColor(self._color)
            glow.setBlurRadius(22)
            glow.setOffset(0, 0)
            self.setGraphicsEffect(glow)
        else:
            self.setGraphicsEffect(None)
        self.update()

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = self.path()
        color = self._color.lighter(135) if self._hovering else self._color
        for alpha, width in [(35, self.LINE_WIDTH + 5), (100, self.LINE_WIDTH + 2), (200, self.LINE_WIDTH)]:
            c = QColor(color)
            c.setAlpha(alpha)
            p.setPen(QPen(c, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
        self._draw_arrowhead(p, path, color)
        self._draw_flow_light(p, path)

    def _draw_arrowhead(self, p: QPainter, path: QPainterPath, color: QColor):
        tip = path.pointAtPercent(1.0)
        back = path.pointAtPercent(0.92)
        dx, dy = tip.x() - back.x(), tip.y() - back.y()
        if dx == 0 and dy == 0:
            return
        angle = math.atan2(dy, dx)
        polygon = _arrow_head_polygon(tip, angle, self.ARROW_SIZE, self.ARROW_SPREAD)
        p.setPen(QPen(color.darker(130), 1))
        p.setBrush(QBrush(color))
        p.drawPolygon(polygon)

    def _draw_flow_light(self, p: QPainter, path: QPainterPath):
        phase = self._overlay.flow_phase
        t0, t1 = max(0.0, phase - _FLOW_SPAN), min(1.0, phase + _FLOW_SPAN)
        if t1 <= t0:
            return
        segment = QPainterPath(path.pointAtPercent(t0))
        steps = 6
        for i in range(1, steps + 1):
            segment.lineTo(path.pointAtPercent(t0 + (t1 - t0) * i / steps))
        halo = QColor(self._color)
        halo.setAlpha(210)
        halo_pen = QPen(halo, self.LINE_WIDTH + 1.6)
        halo_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(halo_pen)
        p.drawPath(segment)
        core_pen = QPen(QColor(255, 255, 255, 235), self.LINE_WIDTH * 0.7)
        core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(core_pen)
        p.drawPath(segment)


class ProgressionMapOverlay:
    """Owns every marker/flow-edge item mirrored onto the real map scene.
    Edges are cheap and torn down/rebuilt wholesale on every rebuild() call;
    markers are matched by node_id and updated in place instead (see
    rebuild()'s docstring — a marker is a real selectable/movable item, so
    swapping its identity out from under an active Selecionar-tool
    interaction is not safe)."""

    def __init__(self, scene_provider):
        self._scene_provider = scene_provider
        self._markers: dict[str, _MapMarkerItem] = {}  # node_id -> item
        self._edges: list[_MapFlowEdgeItem] = []
        self.flow_phase = 0.0
        self._timer = QTimer()
        self._timer.timeout.connect(self._advance)
        self._timer.start(_FLOW_TICK_MS)

    def items(self) -> list:
        """Every marker + edge item currently on the map — for callers that
        only need to enumerate them (e.g. re-applying a hidden-layer
        toggle), not touch identity."""
        return list(self._markers.values()) + self._edges

    def _advance(self):
        if not self._edges:
            return
        self.flow_phase = (self.flow_phase + _FLOW_STEP) % 1.0
        for item in self._edges:
            item.update()

    def clear(self):
        for item in self.items():
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)
        self._markers = {}
        self._edges = []

    def rebuild(self, pipelines: list[dict], on_marker_moved=None, on_marker_remove=None):
        """`pipelines`: list of {"nodes": iterable[_ProgressionNode],
        "edges": iterable[_ProgressionEdge]}. Each marker/edge uses its own
        card's color (node.color — the border color set on the rectangle,
        see items.py), not a fixed per-pipeline color, so the map mirrors
        whatever color each card was actually given. `on_marker_moved(node,
        QPointF)`, when given, is connected to every marker's drag-release
        — see ProgressionMediator._on_marker_dragged. `on_marker_remove(node)`,
        when given, is connected to every marker's ✕ badge — see
        ProgressionMediator._on_marker_remove_requested.

        Markers are matched to their node by node_id and updated in place
        (position/color/icon) rather than torn down and recreated — unlike
        the purely decorative edges, a marker is a real selectable/movable
        item the generic Selecionar tool can pick up (drag, rotate handle,
        the delete/duplicate action bar — see canvas/tools/interaction.py).
        Recreating it out from under an in-progress or just-finished
        interaction left the Selecionar tool's drag/selection/undo state
        holding a reference to an item that had just been silently thrown
        away, which is how a drag settling mid-gesture used to leave a
        stale, orphaned connector line on the map alongside the freshly
        rebuilt one — two arrows into the same pin."""
        scene = self._scene_provider()
        if scene is None:
            self.clear()
            return

        seen_ids = set()
        for pipe in pipelines:
            for node in pipe["nodes"]:
                if not node.pin:
                    continue
                seen_ids.add(node.node_id)
                pos = QPointF(node.pin["x"], node.pin["y"])
                marker = self._markers.get(node.node_id)
                if marker is None:
                    marker = _MapMarkerItem(node, pos, node.color, node.icon)
                    if on_marker_moved is not None:
                        marker.moved.connect(on_marker_moved)
                    if on_marker_remove is not None:
                        marker.remove_requested.connect(on_marker_remove)
                    scene.addItem(marker)
                    self._markers[node.node_id] = marker
                else:
                    if marker.pos() != pos:
                        marker.setPos(pos)
                    marker.set_appearance(node.color, node.icon)

        for node_id in list(self._markers):
            if node_id not in seen_ids:
                item = self._markers.pop(node_id)
                stale_scene = item.scene()
                if stale_scene is not None:
                    stale_scene.removeItem(item)

        # Edges are never selectable (setAcceptedMouseButtons(NoButton) —
        # see _MapFlowEdgeItem) and their whole geometry is just derived
        # from the markers above, so a full teardown/redraw every time is
        # simplest and carries none of the identity-swap risk markers have.
        for item in self._edges:
            stale_scene = item.scene()
            if stale_scene is not None:
                stale_scene.removeItem(item)
        self._edges = []
        for pipe in pipelines:
            for edge in pipe["edges"]:
                if edge.src.pin and edge.dst.pin:
                    a = QPointF(edge.src.pin["x"], edge.src.pin["y"])
                    b = QPointF(edge.dst.pin["x"], edge.dst.pin["y"])
                    line = _MapFlowEdgeItem(a, b, edge.src.color, self)
                    scene.addItem(line)
                    self._edges.append(line)
