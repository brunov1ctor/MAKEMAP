from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from statistics import mean
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, Qt

from src.engines.map.path_engine import PathElement, PathEngine, PathPoint


class WaterType(Enum):
    RIVER = auto()
    STREAM = auto()
    LAKE = auto()
    OCEAN = auto()
    SWAMP = auto()


class ConnectionType(Enum):
    SOURCE = auto()
    MOUTH = auto()
    CONFLUENCE = auto()
    DELTA = auto()
    LAKE_IN = auto()
    LAKE_OUT = auto()


@dataclass
class RiverPoint(PathPoint):
    width: float = 20.0
    depth: float = 1.0   # 0–1
    foam: float = 0.0    # 0–1
    flow_speed: float = 1.0


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
    point_idx: int
    connection_type: ConnectionType
    target_id: Optional[str] = None


@dataclass
class River(PathElement):
    water_type: WaterType = WaterType.RIVER
    style: RiverStyle = field(default_factory=RiverStyle)
    connections: list[WaterConnection] = field(default_factory=list)

    def hit_test(self, point: QPointF, tolerance: float = None) -> bool:
        # rivers sample the path more densely (step 4 vs the base's 5)
        return super().hit_test(point, tolerance=tolerance, sample_step=4)


class RiverEngine(PathEngine[River]):
    def __init__(self):
        super().__init__(default_snap_threshold=15.0)

    def begin_river(self, point: QPointF, width: float = 20.0,
                    water_type: WaterType = WaterType.RIVER,
                    style: RiverStyle = None) -> River:
        river = River(
            water_type=water_type,
            points=[RiverPoint(position=self._snap(point), width=width)],
            style=style or RiverStyle(),
        )
        self._active = river
        return river

    def add_point(self, point: QPointF, width: float = None,
                  depth: float = 1.0, foam: float = 0.0,
                  control_in: QPointF = None, control_out: QPointF = None):
        if not self._active:
            return
        prev = self._active.points[-1]
        w = width if width is not None else prev.width
        self._active.points.append(RiverPoint(
            position=self._snap(point), width=w, depth=depth,
            foam=foam, control_in=control_in, control_out=control_out,
        ))

    def finish_river(self) -> Optional[River]:
        river = self._active
        if river and len(river.points) >= 2:
            self._add(river)
        self._active = None
        return river

    def cancel_river(self):
        self._active = None

    def add_river(self, river: River):
        self._add(river)

    def remove_river(self, river_id: str) -> Optional[River]:
        return self._remove(river_id)

    def get_river(self, river_id: str) -> Optional[River]:
        return self._get(river_id)

    def get_all_rivers(self) -> list[River]:
        return self._get_all()

    def find_river_at(self, point: QPointF) -> Optional[River]:
        return self._find_at(point)

    def set_point_attr(self, river_id: str, idx: int, attr: str, value: float,
                        lo: float = 0.0, hi: float = 1.0):
        super().set_point_attr(river_id, idx, attr, value, lo=lo, hi=hi)

    def set_point_width(self, river_id: str, idx: int, width: float):
        self.set_point_attr(river_id, idx, "width", width, lo=2.0, hi=float("inf"))

    def set_point_depth(self, river_id: str, idx: int, depth: float):
        self.set_point_attr(river_id, idx, "depth", depth)

    def set_point_foam(self, river_id: str, idx: int, foam: float):
        self.set_point_attr(river_id, idx, "foam", foam)

    def insert_point(self, river_id: str, after_idx: int, position: QPointF):
        river = self._items.get(river_id)
        if river and 0 <= after_idx < len(river.points):
            prev = river.points[after_idx]
            river.points.insert(after_idx + 1, RiverPoint(
                position=self._snap(position), width=prev.width, depth=prev.depth))

    def connect_rivers(self, river_id: str, point_idx: int,
                       target_id: str, conn_type: ConnectionType):
        river = self._items.get(river_id)
        if river:
            river.connections.append(WaterConnection(
                river_id=river_id, point_idx=point_idx,
                connection_type=conn_type, target_id=target_id,
            ))

    def _find_incoming_connections(self, river_id: str) -> list[WaterConnection]:
        return [
            c
            for other in self._items.values()
            if other.id != river_id
            for c in other.connections
            if c.target_id == river_id
        ]

    def find_connections(self, river_id: str) -> list[WaterConnection]:
        river = self._items.get(river_id)
        if not river:
            return []
        return list(river.connections) + self._find_incoming_connections(river_id)

    def create_confluence(self, id_a: str, id_b: str) -> bool:
        a = self._items.get(id_a)
        b = self._items.get(id_b)
        if not a or not b:
            return False
        self.connect_rivers(id_a, len(a.points) - 1, id_b, ConnectionType.CONFLUENCE)
        self.connect_rivers(id_b, len(b.points) - 1, id_a, ConnectionType.CONFLUENCE)
        return True

    def create_delta(self, river_id: str, at_idx: int) -> tuple[Optional[River], Optional[River]]:
        river = self._items.get(river_id)
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
        self._remove(river_id)
        self._add(r1)
        self._add(r2)
        return (r1, r2)

    def render_river(self, painter: QPainter, river: River):
        path = river.to_center_path()
        if path.isEmpty():
            return
        painter.save()
        painter.setOpacity(river.style.opacity)
        avg_width = mean(p.width for p in river.points)

        # margem
        if river.style.margin_width > 0:
            self._stroke_path(painter, path, river.style.margin_color,
                               avg_width + river.style.margin_width * 2)

        # corpo d'água com cor baseada na profundidade
        avg_depth = mean(p.depth for p in river.points)
        color = self._blend_color(river.style.color, river.style.deep_color, avg_depth)
        self._stroke_path(painter, path, color, avg_width)

        # espuma nos pontos com foam > 0.2
        for pt in river.points:
            if pt.foam > 0.2:
                self._render_foam(painter, pt, river.style)

        # reflexo
        if river.style.reflection:
            self._render_reflection(painter, path, avg_width, river.style)

        painter.restore()

    def render_all(self, painter: QPainter):
        super().render_all(painter, self.render_river)

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
        channels = [
            int(a + (b - a) * t)
            for a, b in (
                (c1.red(), c2.red()),
                (c1.green(), c2.green()),
                (c1.blue(), c2.blue()),
                (c1.alpha(), c2.alpha()),
            )
        ]
        return QColor(*channels)

    @property
    def river_count(self) -> int:
        return self.count
