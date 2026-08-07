from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from statistics import mean
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen

from src.engines.map.path_engine import PathElement, PathEngine, PathPoint


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
class RoadPoint(PathPoint):
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
class Road(PathElement):
    style: RoadStyle = field(default_factory=RoadStyle)


# ─── Road Engine ─────────────────────────────────────────────────────────────

class RoadEngine(PathEngine[Road]):
    def __init__(self):
        super().__init__(default_snap_threshold=12.0)

    # ─── Road Creation ───────────────────────────────────────────────────

    def begin_road(self, point: QPointF, width: float = 12.0,
                   style: RoadStyle = None) -> Road:
        road = Road(
            points=[RoadPoint(position=self._snap(point), width=width)],
            style=style or RoadStyle(),
        )
        self._active = road
        return road

    def add_point(self, point: QPointF, width: float = None,
                  control_in: QPointF = None, control_out: QPointF = None,
                  segment_type: SegmentType = SegmentType.NORMAL):
        if not self._active:
            return
        prev = self._active.points[-1]
        w = width if width is not None else prev.width
        self._active.points.append(RoadPoint(
            position=self._snap(point), width=w,
            control_in=control_in, control_out=control_out,
            segment_type=segment_type,
        ))

    def finish_road(self) -> Optional[Road]:
        road = self._active
        if road and len(road.points) >= 2:
            self._add(road)
        self._active = None
        return road

    def cancel_road(self):
        self._active = None

    # ─── CRUD ────────────────────────────────────────────────────────────

    def add_road(self, road: Road):
        self._add(road)

    def remove_road(self, road_id: str) -> Optional[Road]:
        return self._remove(road_id)

    def get_road(self, road_id: str) -> Optional[Road]:
        return self._get(road_id)

    def get_all_roads(self) -> list[Road]:
        return self._get_all()

    def find_road_at(self, point: QPointF) -> Optional[Road]:
        return self._find_at(point)

    # ─── Point Editing ───────────────────────────────────────────────────

    def set_point_width(self, road_id: str, idx: int, width: float):
        self.set_point_attr(road_id, idx, "width", width, lo=1.0)

    def set_bezier(self, road_id: str, idx: int,
                   control_in: QPointF = None, control_out: QPointF = None):
        road = self._items.get(road_id)
        if road and 0 <= idx < len(road.points):
            road.points[idx].control_in = control_in
            road.points[idx].control_out = control_out

    def set_segment_type(self, road_id: str, idx: int, seg_type: SegmentType):
        road = self._items.get(road_id)
        if road and 0 <= idx < len(road.points):
            road.points[idx].segment_type = seg_type

    # ─── Intersections & Bifurcations ────────────────────────────────────

    def find_intersections(self, road_id: str) -> list[tuple[str, QPointF]]:
        """Find points where this road is near other roads' endpoints."""
        road = self._items.get(road_id)
        if not road:
            return []
        results = []
        for other in self._items.values():
            if other.id == road_id:
                continue
            for rp in road.points:
                for op in [other.points[0], other.points[-1]]:
                    if (rp.position - op.position).manhattanLength() < self._snap_threshold:
                        results.append((other.id, op.position))
        return results

    def split_road(self, road_id: str, at_idx: int) -> tuple[Optional[Road], Optional[Road]]:
        """Split a road at a given point index into two roads."""
        road = self._items.get(road_id)
        if not road or at_idx <= 0 or at_idx >= len(road.points) - 1:
            return (None, None)
        r1 = Road(name=f"{road.name}_1", points=road.points[:at_idx + 1],
                  style=road.style, layer_id=road.layer_id)
        r2 = Road(name=f"{road.name}_2", points=road.points[at_idx:],
                  style=road.style, layer_id=road.layer_id)
        self._remove(road_id)
        self._add(r1)
        self._add(r2)
        return (r1, r2)

    def join_roads(self, id_a: str, id_b: str) -> Optional[Road]:
        """Join two roads end-to-start."""
        a = self._items.get(id_a)
        b = self._items.get(id_b)
        if not a or not b:
            return None
        joined = Road(name=f"{a.name}+{b.name}",
                      points=a.points + b.points[1:],
                      style=a.style, layer_id=a.layer_id)
        self._remove(id_a)
        self._remove(id_b)
        self._add(joined)
        return joined

    # ─── Rendering ───────────────────────────────────────────────────────

    def render_road(self, painter: QPainter, road: Road):
        path = road.to_center_path()
        if path.isEmpty():
            return
        painter.save()
        painter.setOpacity(road.style.opacity)
        avg_width = mean(p.width for p in road.points)

        # Border
        if road.style.border_width > 0:
            self._stroke_path(painter, path, road.style.border_color,
                               avg_width + road.style.border_width * 2)

        # Main road
        self._stroke_path(painter, path, road.style.color, avg_width,
                           dash_pattern=road.style.dash_pattern)

        # Bridge segments
        for pt in road.points:
            if pt.segment_type == SegmentType.BRIDGE:
                self._render_bridge_marker(painter, pt, road.style)

        painter.restore()

    def render_all(self, painter: QPainter):
        super().render_all(painter, self.render_road)

    def _render_bridge_marker(self, painter: QPainter, pt: RoadPoint, style: RoadStyle):
        """Draw bridge rail indicators at a point."""
        w = pt.width / 2 + 3
        painter.setPen(QPen(style.bridge_rail_color, 2))
        painter.drawLine(
            QPointF(pt.position.x() - w, pt.position.y()),
            QPointF(pt.position.x() + w, pt.position.y()),
        )

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def road_count(self) -> int:
        return self.count
