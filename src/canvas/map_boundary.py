"""MapBoundary — pulsing border overlay for finite map limits, movable by edge drag."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QTimer, QPointF, QLineF
from PySide6.QtGui import QPen, QColor, QPainterPath, QPainterPathStroker
from PySide6.QtWidgets import (
    QGraphicsPathItem, QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsSceneMouseEvent, QGraphicsLineItem,
)

from src.canvas.z_order import ZOrder

# Shapes with a real, discrete corner list — used both to build their path
# (see MapBoundary._build_path) and, distinctly, by TerrainMediator's
# "Livre" insert-mode to let a new point splice into an EXISTING preset's
# corners instead of only ever drawing a polygon from scratch. Circle/
# ellipse/trefoil aren't included: they're curved/overlapping constructions
# with no single natural vertex list.
POLYGON_SHAPES = ("rectangle", "square", "triangle", "hexagon", "pentagon", "star", "cross")


def polygon_vertices_local(shape: str, width: float, height: float) -> list[QPointF] | None:
    """Ordered local-space (centered on origin) corner list for a polygonal
    shape preset, or None if `shape` isn't one of POLYGON_SHAPES."""
    if shape not in POLYGON_SHAPES:
        return None
    half_w, half_h = width / 2, height / 2
    if shape == "square":
        s = min(width, height) / 2
        return [QPointF(-s, -s), QPointF(s, -s), QPointF(s, s), QPointF(-s, s)]
    if shape == "hexagon":
        radius = min(half_w, half_h)
        return [QPointF(radius * math.cos(math.radians(60 * i)), radius * math.sin(math.radians(60 * i)))
                for i in range(6)]
    if shape == "triangle":
        r = min(half_w, half_h)
        return [
            QPointF(0, -r),
            QPointF(r * math.cos(math.radians(210)), r * math.sin(math.radians(210))),
            QPointF(r * math.cos(math.radians(330)), r * math.sin(math.radians(330))),
        ]
    if shape == "pentagon":
        radius = min(half_w, half_h)
        return [QPointF(radius * math.cos(math.radians(-90 + 72 * i)), radius * math.sin(math.radians(-90 + 72 * i)))
                for i in range(5)]
    if shape == "star":
        outer = min(half_w, half_h)
        inner = outer * 0.4
        pts = []
        for i in range(10):
            r = inner if i % 2 else outer
            angle = math.radians(-90 + 36 * i)
            pts.append(QPointF(r * math.cos(angle), r * math.sin(angle)))
        return pts
    if shape == "cross":
        r = min(half_w, half_h)
        t = r * 0.4
        return [QPointF(x, y) for x, y in [
            (-t, -r), (t, -r), (t, -t), (r, -t), (r, t), (t, t),
            (t, r), (-t, r), (-t, t), (-r, t), (-r, -t), (-t, -t),
        ]]
    # rectangle (default)
    return [QPointF(-half_w, -half_h), QPointF(half_w, -half_h), QPointF(half_w, half_h), QPointF(-half_w, half_h)]


def _path_from_vertices(vertices: list[QPointF]) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(vertices[0])
    for pt in vertices[1:]:
        path.lineTo(pt)
    path.closeSubpath()
    return path


# ─── Alignment Guides ────────────────────────────────────────────────────────

class AlignmentGuides:
    """Shows snap alignment lines when boundaries align with each other."""

    SNAP_THRESHOLD = 12.0
    GUIDE_COLOR = QColor(255, 200, 50, 180)
    GUIDE_WIDTH = 1.5
    EXTENT = 50000

    def __init__(self, scene: QGraphicsScene):
        self._scene = scene
        self._lines: list[QGraphicsLineItem] = []

    def update(self, moving_item: "MovableBoundaryItem", all_items: list["MovableBoundaryItem"]) -> QPointF:
        """Calculate guides and return snap offset."""
        self.clear()
        if not moving_item:
            return QPointF(0, 0)

        moving_rect = moving_item.mapToScene(moving_item.boundingRect()).boundingRect()
        snap_dx = 0.0
        snap_dy = 0.0

        m_cx = moving_rect.center().x()
        m_cy = moving_rect.center().y()
        m_left = moving_rect.left()
        m_right = moving_rect.right()
        m_top = moving_rect.top()
        m_bottom = moving_rect.bottom()

        for other in all_items:
            if other is moving_item or not other.isVisible():
                continue
            r = other.mapToScene(other.boundingRect()).boundingRect()
            o_cx, o_cy = r.center().x(), r.center().y()
            o_left, o_right = r.left(), r.right()
            o_top, o_bottom = r.top(), r.bottom()

            # Vertical alignment (X axis)
            for m_x, o_x in [(m_cx, o_cx), (m_left, o_left), (m_right, o_right),
                             (m_left, o_right), (m_right, o_left)]:
                if abs(m_x - o_x) < self.SNAP_THRESHOLD:
                    if snap_dx == 0.0:
                        snap_dx = o_x - m_x
                    self._add_vline(o_x)

            # Horizontal alignment (Y axis)
            for m_y, o_y in [(m_cy, o_cy), (m_top, o_top), (m_bottom, o_bottom),
                             (m_top, o_bottom), (m_bottom, o_top)]:
                if abs(m_y - o_y) < self.SNAP_THRESHOLD:
                    if snap_dy == 0.0:
                        snap_dy = o_y - m_y
                    self._add_hline(o_y)

        return QPointF(snap_dx, snap_dy)

    def clear(self):
        for line in self._lines:
            if line.scene():
                self._scene.removeItem(line)
        self._lines.clear()

    def _add_vline(self, x: float):
        line = QGraphicsLineItem(QLineF(x, -self.EXTENT, x, self.EXTENT))
        pen = QPen(self.GUIDE_COLOR, self.GUIDE_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(ZOrder.CURSOR_GHOST)
        self._scene.addItem(line)
        self._lines.append(line)

    def _add_hline(self, y: float):
        line = QGraphicsLineItem(QLineF(-self.EXTENT, y, self.EXTENT, y))
        pen = QPen(self.GUIDE_COLOR, self.GUIDE_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(ZOrder.CURSOR_GHOST)
        self._scene.addItem(line)
        self._lines.append(line)


# ─── Movable Boundary Item ───────────────────────────────────────────────────

class MovableBoundaryItem(QGraphicsPathItem):
    """Path item that can be moved by dragging its border stroke area."""

    HIT_WIDTH = 20.0

    def __init__(self, path: QPainterPath, parent=None):
        super().__init__(path, parent)
        self._dragging = False
        self._hovered = False
        self._drag_start_scene = QPointF()
        self._drag_start_pos = QPointF()
        self._guides: AlignmentGuides | None = None
        # Plain callback, not a Qt signal — QGraphicsPathItem isn't a
        # QObject, and a new instance replaces this one on every
        # show()/update_dimensions()/update_shape() (see MapBoundary._rebuild),
        # so MapBoundary rewires this each time rather than this item
        # owning a persistent connection.
        self.on_moved = None
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def _hit_border(self, pos: QPointF) -> bool:
        """Check if pos is near the border stroke."""
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        stroke_area = stroker.createStroke(self.path())
        return stroke_area.contains(pos)

    def hoverEnterEvent(self, event):
        if self._hit_border(event.pos()):
            self._set_hovered(True)
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        on_border = self._hit_border(event.pos())
        if on_border:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            if not self._hovered:
                self._set_hovered(True)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._hovered:
                self._set_hovered(False)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._set_hovered(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(event)

    def _set_hovered(self, hovered: bool):
        self._hovered = hovered
        pen = self.pen()
        if hovered:
            pen.setWidthF(5.0)
            pen.setStyle(Qt.PenStyle.SolidLine)
            color = pen.color()
            color.setAlpha(255)
            pen.setColor(color)
        else:
            pen.setWidthF(3.0)
            pen.setStyle(Qt.PenStyle.DashDotLine)
        self.setPen(pen)
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._hit_border(event.pos()):
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            self._drag_start_pos = self.parentItem().pos() if self.parentItem() else self.pos()
            if self.scene():
                self._guides = AlignmentGuides(self.scene())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            new_pos = self._drag_start_pos + delta
            parent = self.parentItem()
            if parent:
                parent.setPos(new_pos)
            else:
                self.setPos(new_pos)
            if self._guides and self.scene():
                others = [item for item in self.scene().items()
                          if isinstance(item, MovableBoundaryItem) and item is not self]
                snap_offset = self._guides.update(self, others)
                if snap_offset.x() != 0 or snap_offset.y() != 0:
                    if parent:
                        parent.setPos(new_pos + snap_offset)
                    else:
                        self.setPos(new_pos + snap_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            self._dragging = False
            if self._guides:
                self._guides.clear()
                self._guides = None
            if self.on_moved:
                pos = self.parentItem().pos() if self.parentItem() else self.pos()
                self.on_moved(pos)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


# ─── Map Boundary ────────────────────────────────────────────────────────────

class MapBoundary:
    """Draws a pulsing border on the scene to show map limits."""

    PULSE_MIN_ALPHA = 60
    PULSE_MAX_ALPHA = 200
    PULSE_INTERVAL_MS = 50
    PULSE_CYCLE_MS = 1500
    BORDER_WIDTH = 3.0
    BORDER_COLOR_BASE = QColor(79, 195, 247)

    # Keep numerically identical to TerrainSettingsPanel.DEFAULT_* —
    # not cross-imported to avoid coupling canvas/ to layouts/.
    DEFAULT_SHAPE = "rectangle"
    DEFAULT_WIDTH = 4096
    DEFAULT_HEIGHT = 4096

    def __init__(self, scene: QGraphicsScene, color: QColor = None):
        self._scene = scene
        # Stable container — added to scene only on show(), removed on hide().
        self._group = QGraphicsItemGroup()
        self._group.setZValue(ZOrder.BOUNDARY_GROUP)
        self._group.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._group.setHandlesChildEvents(False)
        # NOT added to scene here — only when show()/set_points() is called.
        self._item: MovableBoundaryItem | None = None
        self._visible = False
        self._shape = self.DEFAULT_SHAPE
        self._width = self.DEFAULT_WIDTH
        self._height = self.DEFAULT_HEIGHT
        self._color = color or self.BORDER_COLOR_BASE
        self._preview = False
        self._points: list[QPointF] = []  # only used when self._shape == "freehand"
        # segment start index -> Bézier control point (scene coords) — only
        # used when self._shape == "freehand"; see set_points.
        self._curve_controls: dict[int, QPointF] = {}
        self._on_position_changed = None  # set via set_on_position_changed

        # Pulse animation state
        self._alpha = self.PULSE_MIN_ALPHA
        self._alpha_dir = 1
        self._timer = QTimer()
        self._timer.setInterval(self.PULSE_INTERVAL_MS)
        self._timer.timeout.connect(self._pulse_tick)

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def shape(self) -> str:
        return self._shape

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def group(self) -> QGraphicsItemGroup:
        """Stable content container — parent scene items here instead of
        to _item so they survive _rebuild() replacing the border item."""
        return self._group

    @property
    def position(self) -> QPointF:
        return self._group.pos()

    def set_position(self, pos: QPointF):
        self._group.setPos(pos)

    def contains_point(self, scene_pos: QPointF) -> bool:
        if not self._item:
            return False
        local = self._item.mapFromScene(scene_pos)
        return self._item.path().contains(local)

    def set_on_position_changed(self, callback):
        """`callback(QPointF)` fires when the user finishes dragging this
        boundary — used by TerrainMediator to persist the new position.
        Rewired onto the live item every _rebuild() (see there) since
        show()/update_dimensions()/update_shape() all replace the item."""
        self._on_position_changed = callback
        if self._item:
            self._item.on_moved = callback

    def show(self, width: int, height: int, shape: str = "rectangle"):
        self._width = width
        self._height = height
        self._shape = shape
        self._visible = True
        self._preview = False
        if not self._group.scene():
            self._scene.addItem(self._group)
        self._rebuild()
        self._timer.start()

    def hide(self):
        self._visible = False
        self._preview = False
        self._timer.stop()
        if self._item:
            self._item.setParentItem(None)
            if self._item.scene():
                self._scene.removeItem(self._item)
            self._item = None
        if self._group.scene():
            # Remove content children from the scene along with the group
            # — pintura some junto com o terreno ao excluir.
            for child in list(self._group.childItems()):
                if child.scene():
                    self._scene.removeItem(child)
            self._scene.removeItem(self._group)

    def update_dimensions(self, width: int, height: int):
        self._width = width
        self._height = height
        if self._visible:
            self._rebuild()

    def set_color(self, color: QColor):
        self._color = color
        self._update_pen()

    def update_shape(self, shape: str):
        self._shape = shape
        if self._visible:
            self._rebuild()

    @property
    def points(self) -> list[QPointF]:
        return list(self._points)

    def polygon_vertices_scene(self) -> list[QPointF] | None:
        pos = self._group.pos()
        if self._shape == "freehand":
            if not self._points:
                return None
            local = self._points
        else:
            local = polygon_vertices_local(self._shape, self._width, self._height)
            if local is None:
                return None
        return [QPointF(p.x() + pos.x(), p.y() + pos.y()) for p in local]

    def set_points(self, points: list[QPointF], curve_controls: dict[int, QPointF] | None = None):
        self._shape = "freehand"
        self._points = list(points)
        self._curve_controls = dict(curve_controls) if curve_controls else {}
        self._visible = True
        self._preview = False
        self._group.setPos(QPointF(0, 0))
        if not self._group.scene():
            self._scene.addItem(self._group)
        self._rebuild()
        if not self._timer.isActive():
            self._timer.start()

    def _rebuild(self):
        # Remove old border item without touching the group or its children.
        if self._item:
            self._item.setParentItem(None)
            if self._item.scene():
                self._scene.removeItem(self._item)

        path = self._build_path()
        self._item = MovableBoundaryItem(path)
        self._item.setZValue(ZOrder.BOUNDARY_OUTLINE)
        self._item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._item.on_moved = self._on_position_changed
        self._update_pen()
        self._item.setParentItem(self._group)

    def _build_path(self) -> QPainterPath:
        path = QPainterPath()

        if self._shape == "freehand":
            if len(self._points) >= 2:
                path.moveTo(self._points[0])
                for i, pt in enumerate(self._points[1:]):
                    control = self._curve_controls.get(i)
                    if control is not None:
                        path.quadTo(control, pt)
                    else:
                        path.lineTo(pt)
                path.closeSubpath()
            elif len(self._points) == 1:
                # A single point has no area yet — draw it as a tiny dot so
                # something still reads as "drawing has started".
                p = self._points[0]
                path.addEllipse(p, 2, 2)
            return path

        half_w = self._width / 2
        half_h = self._height / 2

        poly = polygon_vertices_local(self._shape, self._width, self._height)
        if poly is not None:
            return _path_from_vertices(poly)

        if self._shape == "circle":
            radius = min(half_w, half_h)
            path.addEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
        elif self._shape == "ellipse":
            path.addEllipse(QRectF(-half_w, -half_h, self._width, self._height))
        elif self._shape == "trefoil":
            r = min(half_w, half_h)
            lobe_r = r * 0.55
            offset = r * 0.5
            for angle_deg in (-90, 30, 150):
                angle = math.radians(angle_deg)
                cx, cy = offset * math.cos(angle), offset * math.sin(angle)
                path.addEllipse(QRectF(cx - lobe_r, cy - lobe_r, lobe_r * 2, lobe_r * 2))
            path.addEllipse(QRectF(-offset * 0.9, -offset * 0.9, offset * 1.8, offset * 1.8))
            # Overlapping lobes as separate subpaths would leave holes under
            # the default odd-even fill (double-covered regions toggle back
            # to "outside") — winding fill keeps any positive-covered area
            # solid, reading as one fused clover shape instead.
            path.setFillRule(Qt.FillRule.WindingFill)
        else:
            path.addRect(QRectF(-half_w, -half_h, self._width, self._height))

        return path

    def _update_pen(self):
        if not self._item:
            return
        if self._preview:
            color = QColor(self._color)
            color.setAlpha(140)
            pen = QPen(color, 2.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._item.setPen(pen)
            return
        color = QColor(self._color)
        color.setAlpha(int(self._alpha))
        pen = QPen(color, self.BORDER_WIDTH, Qt.PenStyle.DashDotLine)
        pen.setCosmetic(True)
        self._item.setPen(pen)

    def _pulse_tick(self):
        step = ((self.PULSE_MAX_ALPHA - self.PULSE_MIN_ALPHA) /
                (self.PULSE_CYCLE_MS / self.PULSE_INTERVAL_MS / 2))
        self._alpha += step * self._alpha_dir

        if self._alpha >= self.PULSE_MAX_ALPHA:
            self._alpha = self.PULSE_MAX_ALPHA
            self._alpha_dir = -1
        elif self._alpha <= self.PULSE_MIN_ALPHA:
            self._alpha = self.PULSE_MIN_ALPHA
            self._alpha_dir = 1

        self._update_pen()
