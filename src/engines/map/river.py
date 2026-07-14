"""FASE 17 — River Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (QColor, QPainter, QPainterPath, QPen, QBrush,
                            QLinearGradient, QRadialGradient, Qt)


# ─── Enums ───────────────────────────────────────────────────────────────────

class WaterType(Enum):
    RIVER = auto()
    STREAM = auto()
    LAKE = auto()
    OCEAN = auto()
    SWAMP = auto()


class ConnectionType(Enum):
    SOURCE = auto()       # Nascente
    MOUTH = auto()        # Foz
    CONFLUENCE = auto()   # Rios que se juntam
    DELTA = auto()        # Rio que se divide
    LAKE_IN = auto()
    LAKE_OUT = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class RiverPoint:
    position: QPointF
    control_in: Optional[QPointF] = None
    control_out: Optional[QPointF] = None
    width: float = 20.0
    depth: float = 1.0        # 0-1, affects color darkness
    foam: float = 0.0         # 0-1, foam intensity at this point
    flow_speed: float = 1.0   # relative speed


@dataclass
class RiverStyle:
    color: QColor = field(default_factory=lambda: QColor(60, 130, 180, 200))
    deep_color: QColor = field(default_factory=lambda: QColor(20, 60, 100, 220))
    margin_color: QColor = field(default_factory=lambda: QColor(80, 140, 80, 150))
    foam_color: QColor = field(default_factory=lambda: QColor(220, 240, 255, 180))
    margin_width: float = 4.0
    opacity: float = 0.85
    reflection: bool = True
    reflection_opacity: float = 0.3


@dataclass
class WaterConnection:
    river_id: str
    point_idx: int  # which point connects
    connection_type: ConnectionType
    target_id: Optional[str] = None  # connected river/lake id


@dataclass
class River:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    water_type: WaterType = WaterType.RIVER
    points: list[RiverPoint] = field(default_factory=list)
    style: RiverStyle = field(default_factory=RiverStyle)
    connections: list[WaterConnection] = field(default_factory=list)
    closed: bool = False  # True for lakes
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
            path.lineTo(self.points[0].position)
            path.closeSubpath()
        return path

    def hit_test(self, point: QPointF) -> bool:
        if not self.points:
            return False
        path = self.to_center_path()
        max_w = max(p.width for p in self.points) / 2 + 4
        if not self.bounding_rect().adjusted(-max_w, -max_w, max_w, max_w).contains(point):
            return False
        for t in range(0, 101, 4):
            pt = path.pointAtPercent(t / 100.0)
            if (pt - point).manhattanLength() < max_w:
                return True
        return False

    def find_point(self, pos: QPointF, tolerance: float = 10.0) -> int:
        for i, p in enumerate(self.points):
            if (p.position - pos).manhattanLength() < tolerance:
                return i
        return -1


# ─── River Engine ────────────────────────────────────────────────────────────

class RiverEngine:
    def __init__(self):
        self._rivers: dict[str, River] = {}
        self._active_river: Optional[River] = None
        self._snap_enabled: bool = True
        self._snap_threshold: float = 15.0

    # ─── Creation ────────────────────────────────────────────────────────

    def begin_river(self, point: QPointF, width: float = 20.0,
                    water_type: WaterType = WaterType.RIVER,
                    style: RiverStyle = None) -> River:
        river = River(
            water_type=water_type,
            points=[RiverPoint(position=self._snap(point), width=width)],
            style=style or RiverStyle(),
        )
        self._active_river = river
        return river

    def add_point(self, point: QPointF, width: float = None,
                  depth: float = 1.0, foam: float = 0.0,
                  control_in: QPointF = None, control_out: QPointF = None):
        if not self._active_river:
            return
        prev = self._active_river.points[-1]
        w = width if width is not None else prev.width
        self._active_river.points.append(RiverPoint(
            position=self._snap(point), width=w, depth=depth,
            foam=foam, control_in=control_in, control_out=control_out,
        ))

    def finish_river(self) -> Optional[River]:
        river = self._active_river
        if river and len(river.points) >= 2:
            self._rivers[river.id] = river
        self._active_river = None
        return river

    def cancel_river(self):
        self._active_river = None

    # ─── CRUD ────────────────────────────────────────────────────────────

    def add_river(self, river: River):
        self._rivers[river.id] = river

    def remove_river(self, river_id: str) -> Optional[River]:
        return self._rivers.pop(river_id, None)

    def get_river(self, river_id: str) -> Optional[River]:
        return self._rivers.get(river_id)

    def get_all_rivers(self) -> list[River]:
        return list(self._rivers.values())

    def find_river_at(self, point: QPointF) -> Optional[River]:
        for river in reversed(list(self._rivers.values())):
            if river.hit_test(point):
                return river
        return None

    # ─── Point Editing ───────────────────────────────────────────────────

    def move_point(self, river_id: str, idx: int, new_pos: QPointF):
        river = self._rivers.get(river_id)
        if river and 0 <= idx < len(river.points):
            river.points[idx].position = self._snap(new_pos)

    def set_point_width(self, river_id: str, idx: int, width: float):
        river = self._rivers.get(river_id)
        if river and 0 <= idx < len(river.points):
            river.points[idx].width = max(2.0, width)

    def set_point_depth(self, river_id: str, idx: int, depth: float):
        river = self._rivers.get(river_id)
        if river and 0 <= idx < len(river.points):
            river.points[idx].depth = max(0.0, min(1.0, depth))

    def set_point_foam(self, river_id: str, idx: int, foam: float):
        river = self._rivers.get(river_id)
        if river and 0 <= idx < len(river.points):
            river.points[idx].foam = max(0.0, min(1.0, foam))

    def insert_point(self, river_id: str, after_idx: int, position: QPointF):
        river = self._rivers.get(river_id)
        if river and 0 <= after_idx < len(river.points):
            prev = river.points[after_idx]
            river.points.insert(after_idx + 1, RiverPoint(
                position=self._snap(position), width=prev.width, depth=prev.depth))

    def remove_point(self, river_id: str, idx: int):
        river = self._rivers.get(river_id)
        if river and len(river.points) > 2 and 0 <= idx < len(river.points):
            river.points.pop(idx)

    # ─── Connections ─────────────────────────────────────────────────────

    def connect_rivers(self, river_id: str, point_idx: int,
                       target_id: str, conn_type: ConnectionType):
        river = self._rivers.get(river_id)
        if river:
            river.connections.append(WaterConnection(
                river_id=river_id, point_idx=point_idx,
                connection_type=conn_type, target_id=target_id,
            ))

    def find_connections(self, river_id: str) -> list[WaterConnection]:
        river = self._rivers.get(river_id)
        if not river:
            return []
        conns = list(river.connections)
        # Also find other rivers connecting to this one
        for other in self._rivers.values():
            if other.id == river_id:
                continue
            for c in other.connections:
                if c.target_id == river_id:
                    conns.append(c)
        return conns

    def create_confluence(self, id_a: str, id_b: str, merge_point: QPointF) -> Optional[River]:
        """Two rivers merge into one at merge_point."""
        a = self._rivers.get(id_a)
        b = self._rivers.get(id_b)
        if not a or not b:
            return None
        self.connect_rivers(id_a, len(a.points) - 1, id_b, ConnectionType.CONFLUENCE)
        self.connect_rivers(id_b, len(b.points) - 1, id_a, ConnectionType.CONFLUENCE)
        return a

    def create_delta(self, river_id: str, at_idx: int) -> tuple[Optional[River], Optional[River]]:
        """Split river into two branches at a point."""
        river = self._rivers.get(river_id)
        if not river or at_idx <= 0 or at_idx >= len(river.points) - 1:
            return (None, None)
        r1 = River(name=f"{river.name}_L", water_type=river.water_type,
                   points=river.points[:at_idx + 1], style=river.style,
                   layer_id=river.layer_id)
        r2 = River(name=f"{river.name}_R", water_type=river.water_type,
                   points=river.points[at_idx:], style=river.style,
                   layer_id=river.layer_id)
        r1.connections.append(WaterConnection(
            river_id=r1.id, point_idx=at_idx,
            connection_type=ConnectionType.DELTA, target_id=r2.id))
        self._rivers.pop(river_id)
        self._rivers[r1.id] = r1
        self._rivers[r2.id] = r2
        return (r1, r2)

    # ─── Rendering ───────────────────────────────────────────────────────

    def render_river(self, painter: QPainter, river: River):
        path = river.to_center_path()
        if path.isEmpty():
            return
        painter.save()
        painter.setOpacity(river.style.opacity)
        avg_width = sum(p.width for p in river.points) / len(river.points)

        # Margin
        if river.style.margin_width > 0:
            pen = QPen(river.style.margin_color, avg_width + river.style.margin_width * 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        # Main water body — gradient based on depth
        avg_depth = sum(p.depth for p in river.points) / len(river.points)
        color = self._blend_color(river.style.color, river.style.deep_color, avg_depth)
        pen = QPen(color, avg_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # Foam at high-foam points
        for pt in river.points:
            if pt.foam > 0.2:
                self._render_foam(painter, pt, river.style)

        # Reflection highlight
        if river.style.reflection:
            self._render_reflection(painter, path, avg_width, river.style)

        painter.restore()

    def render_all(self, painter: QPainter):
        for river in self._rivers.values():
            self.render_river(painter, river)

    def _render_foam(self, painter: QPainter, pt: RiverPoint, style: RiverStyle):
        foam_color = QColor(style.foam_color)
        foam_color.setAlphaF(pt.foam * 0.7)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(foam_color))
        r = pt.width * 0.3 * pt.foam
        painter.drawEllipse(pt.position, r, r * 0.6)

    def _render_reflection(self, painter: QPainter, path: QPainterPath,
                           width: float, style: RiverStyle):
        ref_color = QColor(255, 255, 255, int(style.reflection_opacity * 80))
        pen = QPen(ref_color, width * 0.3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

    @staticmethod
    def _blend_color(c1: QColor, c2: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
            int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
        )

    # ─── Snap ────────────────────────────────────────────────────────────

    def set_snap(self, enabled: bool, threshold: float = 15.0):
        self._snap_enabled = enabled
        self._snap_threshold = threshold

    def _snap(self, point: QPointF) -> QPointF:
        if not self._snap_enabled or not self._rivers:
            return point
        closest = None
        min_dist = self._snap_threshold
        for river in self._rivers.values():
            for p in river.points:
                dist = (p.position - point).manhattanLength()
                if dist < min_dist:
                    min_dist = dist
                    closest = p.position
        return QPointF(closest) if closest else point

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def river_count(self) -> int:
        return len(self._rivers)
