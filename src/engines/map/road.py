"""FASE 16 — Road Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, Qt


# ─── Enums ───────────────────────────────────────────────────────────────────

class RoadTexture(Enum):
    DIRT = auto()
    STONE = auto()
    COBBLE = auto()
    PAVED = auto()
    SAND = auto()
    GRASS_PATH = auto()
    CUSTOM = auto()


class SegmentType(Enum):
    NORMAL = auto()
    BRIDGE = auto()
    TUNNEL = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class RoadPoint:
    position: QPointF
    control_in: Optional[QPointF] = None
    control_out: Optional[QPointF] = None
    width: float = 12.0
    segment_type: SegmentType = SegmentType.NORMAL

    @property
    def is_bezier(self) -> bool:
        return self.control_in is not None or self.control_out is not None


@dataclass
class RoadStyle:
    texture: RoadTexture = RoadTexture.DIRT
    color: QColor = field(default_factory=lambda: QColor(139, 119, 85))
    border_color: QColor = field(default_factory=lambda: QColor(90, 75, 55))
    border_width: float = 2.0
    opacity: float = 1.0
    dash_pattern: Optional[list[float]] = None  # e.g. [10, 5] for dashed
    bridge_color: QColor = field(default_factory=lambda: QColor(120, 100, 70))
    bridge_rail_color: QColor = field(default_factory=lambda: QColor(80, 60, 40))


@dataclass
class Road:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    points: list[RoadPoint] = field(default_factory=list)
    style: RoadStyle = field(default_factory=RoadStyle)
    closed: bool = False
    layer_id: Optional[str] = None

    def bounding_rect(self) -> QRectF:
        if not self.points:
            return QRectF()
        max_w = max(p.width for p in self.points)
        xs = [p.position.x() for p in self.points]
        ys = [p.position.y() for p in self.points]
        return QRectF(min(xs) - max_w, min(ys) - max_w,
                      max(xs) - min(xs) + max_w * 2,
                      max(ys) - min(ys) + max_w * 2)

    def to_center_path(self) -> QPainterPath:
        path = QPainterPath()
        if len(self.points) < 2:
            return path
        path.moveTo(self.points[0].position)
        for i in range(1, len(self.points)):
            prev = self.points[i - 1]
            curr = self.points[i]
            if prev.control_out and curr.control_in:
                path.cubicTo(prev.control_out, curr.control_in, curr.position)
            elif prev.control_out:
                path.quadTo(prev.control_out, curr.position)
            elif curr.control_in:
                path.quadTo(curr.control_in, curr.position)
            else:
                path.lineTo(curr.position)
        if self.closed and len(self.points) > 2:
            last = self.points[-1]
            first = self.points[0]
            if last.control_out and first.control_in:
                path.cubicTo(last.control_out, first.control_in, first.position)
            else:
                path.lineTo(first.position)
            path.closeSubpath()
        return path

    def hit_test(self, point: QPointF, tolerance: float = None) -> bool:
        if not self.points:
            return False
        path = self.to_center_path()
        max_w = max(p.width for p in self.points) / 2
        tol = tolerance if tolerance else max_w + 4
        # Check distance to path via stroker
        stroker = QPainterPath()
        stroker.addPath(path)
        # Simple: check bounding + point proximity to segments
        if not self.bounding_rect().adjusted(-tol, -tol, tol, tol).contains(point):
            return False
        for p in self.points:
            if (p.position - point).manhattanLength() < tol:
                return True
        # Sample path
        for t in range(0, 101, 5):
            pt = path.pointAtPercent(t / 100.0)
            if (pt - point).manhattanLength() < tol:
                return True
        return False

    def find_point(self, pos: QPointF, tolerance: float = 10.0) -> int:
        for i, p in enumerate(self.points):
            if (p.position - pos).manhattanLength() < tolerance:
                return i
        return -1


# ─── Road Engine ─────────────────────────────────────────────────────────────

class RoadEngine:
    def __init__(self):
        self._roads: dict[str, Road] = {}
        self._active_road: Optional[Road] = None
        self._snap_enabled: bool = True
        self._snap_threshold: float = 12.0

    # ─── Road Creation ───────────────────────────────────────────────────

    def begin_road(self, point: QPointF, width: float = 12.0,
                   style: RoadStyle = None) -> Road:
        road = Road(
            points=[RoadPoint(position=self._snap(point), width=width)],
            style=style or RoadStyle(),
        )
        self._active_road = road
        return road

    def add_point(self, point: QPointF, width: float = None,
                  control_in: QPointF = None, control_out: QPointF = None,
                  segment_type: SegmentType = SegmentType.NORMAL):
        if not self._active_road:
            return
        prev = self._active_road.points[-1]
        w = width if width is not None else prev.width
        self._active_road.points.append(RoadPoint(
            position=self._snap(point), width=w,
            control_in=control_in, control_out=control_out,
            segment_type=segment_type,
        ))

    def finish_road(self) -> Optional[Road]:
        road = self._active_road
        if road and len(road.points) >= 2:
            self._roads[road.id] = road
        self._active_road = None
        return road

    def cancel_road(self):
        self._active_road = None

    # ─── CRUD ────────────────────────────────────────────────────────────

    def add_road(self, road: Road):
        self._roads[road.id] = road

    def remove_road(self, road_id: str) -> Optional[Road]:
        return self._roads.pop(road_id, None)

    def get_road(self, road_id: str) -> Optional[Road]:
        return self._roads.get(road_id)

    def get_all_roads(self) -> list[Road]:
        return list(self._roads.values())

    def find_road_at(self, point: QPointF) -> Optional[Road]:
        for road in reversed(list(self._roads.values())):
            if road.hit_test(point):
                return road
        return None

    # ─── Point Editing ───────────────────────────────────────────────────

    def move_point(self, road_id: str, idx: int, new_pos: QPointF):
        road = self._roads.get(road_id)
        if road and 0 <= idx < len(road.points):
            road.points[idx].position = self._snap(new_pos)

    def set_point_width(self, road_id: str, idx: int, width: float):
        road = self._roads.get(road_id)
        if road and 0 <= idx < len(road.points):
            road.points[idx].width = max(1.0, width)

    def set_bezier(self, road_id: str, idx: int,
                   control_in: QPointF = None, control_out: QPointF = None):
        road = self._roads.get(road_id)
        if road and 0 <= idx < len(road.points):
            road.points[idx].control_in = control_in
            road.points[idx].control_out = control_out

    def set_segment_type(self, road_id: str, idx: int, seg_type: SegmentType):
        road = self._roads.get(road_id)
        if road and 0 <= idx < len(road.points):
            road.points[idx].segment_type = seg_type

    def insert_point(self, road_id: str, after_idx: int, position: QPointF):
        road = self._roads.get(road_id)
        if road and 0 <= after_idx < len(road.points):
            prev = road.points[after_idx]
            road.points.insert(after_idx + 1, RoadPoint(
                position=self._snap(position), width=prev.width))

    def remove_point(self, road_id: str, idx: int):
        road = self._roads.get(road_id)
        if road and len(road.points) > 2 and 0 <= idx < len(road.points):
            road.points.pop(idx)

    # ─── Intersections & Bifurcations ────────────────────────────────────

    def find_intersections(self, road_id: str) -> list[tuple[str, QPointF]]:
        """Find points where this road is near other roads' endpoints."""
        road = self._roads.get(road_id)
        if not road:
            return []
        results = []
        for other in self._roads.values():
            if other.id == road_id:
                continue
            for rp in road.points:
                for op in [other.points[0], other.points[-1]]:
                    if (rp.position - op.position).manhattanLength() < self._snap_threshold:
                        results.append((other.id, op.position))
        return results

    def split_road(self, road_id: str, at_idx: int) -> tuple[Optional[Road], Optional[Road]]:
        """Split a road at a given point index into two roads."""
        road = self._roads.get(road_id)
        if not road or at_idx <= 0 or at_idx >= len(road.points) - 1:
            return (None, None)
        r1 = Road(name=f"{road.name}_1", points=road.points[:at_idx + 1],
                  style=road.style, layer_id=road.layer_id)
        r2 = Road(name=f"{road.name}_2", points=road.points[at_idx:],
                  style=road.style, layer_id=road.layer_id)
        self._roads.pop(road_id)
        self._roads[r1.id] = r1
        self._roads[r2.id] = r2
        return (r1, r2)

    def join_roads(self, id_a: str, id_b: str) -> Optional[Road]:
        """Join two roads end-to-start."""
        a = self._roads.get(id_a)
        b = self._roads.get(id_b)
        if not a or not b:
            return None
        joined = Road(name=f"{a.name}+{b.name}",
                      points=a.points + b.points[1:],
                      style=a.style, layer_id=a.layer_id)
        self._roads.pop(id_a)
        self._roads.pop(id_b)
        self._roads[joined.id] = joined
        return joined

    # ─── Rendering ───────────────────────────────────────────────────────

    def render_road(self, painter: QPainter, road: Road):
        path = road.to_center_path()
        if path.isEmpty():
            return
        painter.save()
        painter.setOpacity(road.style.opacity)
        avg_width = sum(p.width for p in road.points) / len(road.points)

        # Border
        if road.style.border_width > 0:
            pen = QPen(road.style.border_color, avg_width + road.style.border_width * 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        # Main road
        pen = QPen(road.style.color, avg_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if road.style.dash_pattern:
            pen.setDashPattern(road.style.dash_pattern)
        painter.setPen(pen)
        painter.drawPath(path)

        # Bridge segments
        for i, pt in enumerate(road.points):
            if pt.segment_type == SegmentType.BRIDGE:
                self._render_bridge_marker(painter, pt, road.style)

        painter.restore()

    def render_all(self, painter: QPainter):
        for road in self._roads.values():
            self.render_road(painter, road)

    def _render_bridge_marker(self, painter: QPainter, pt: RoadPoint, style: RoadStyle):
        """Draw bridge rail indicators at a point."""
        w = pt.width / 2 + 3
        painter.setPen(QPen(style.bridge_rail_color, 2))
        painter.drawLine(
            QPointF(pt.position.x() - w, pt.position.y()),
            QPointF(pt.position.x() + w, pt.position.y()),
        )

    # ─── Snap ────────────────────────────────────────────────────────────

    def set_snap(self, enabled: bool, threshold: float = 12.0):
        self._snap_enabled = enabled
        self._snap_threshold = threshold

    def _snap(self, point: QPointF) -> QPointF:
        if not self._snap_enabled or not self._roads:
            return point
        closest = None
        min_dist = self._snap_threshold
        for road in self._roads.values():
            for p in road.points:
                dist = (p.position - point).manhattanLength()
                if dist < min_dist:
                    min_dist = dist
                    closest = p.position
        return QPointF(closest) if closest else point

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def road_count(self) -> int:
        return len(self._roads)
