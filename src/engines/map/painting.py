"""FASE 15 — Painting Engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen, QBrush, QLinearGradient, QPainter, QPolygonF


# ─── Enums ───────────────────────────────────────────────────────────────────

class PaintMode(Enum):
    PAINT = auto()
    ERASE = auto()
    MASK = auto()
    ALPHA = auto()


class FillType(Enum):
    SOLID = auto()
    GRADIENT = auto()
    PATTERN = auto()


class PatternType(Enum):
    NONE = auto()
    HATCH = auto()
    DOTS = auto()
    CROSS_HATCH = auto()
    DIAGONAL = auto()


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class Vertex:
    position: QPointF
    control_in: Optional[QPointF] = None
    control_out: Optional[QPointF] = None

    @property
    def is_bezier(self) -> bool:
        return self.control_in is not None or self.control_out is not None


@dataclass
class PaintStroke:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: PaintMode = PaintMode.PAINT
    points: list[QPointF] = field(default_factory=list)
    color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    size: float = 10.0
    opacity: float = 1.0
    hardness: float = 0.8
    target_layer: Optional[str] = None


@dataclass
class RegionPolygon:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    vertices: list[Vertex] = field(default_factory=list)
    closed: bool = True
    fill_color: QColor = field(default_factory=lambda: QColor(100, 150, 200, 80))
    fill_type: FillType = FillType.SOLID
    gradient_start: QColor = field(default_factory=lambda: QColor(100, 150, 200, 80))
    gradient_end: QColor = field(default_factory=lambda: QColor(50, 100, 150, 40))
    pattern: PatternType = PatternType.NONE
    border_color: QColor = field(default_factory=lambda: QColor(200, 220, 255, 180))
    border_width: float = 2.0
    opacity: float = 0.6
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None  # Region, Kingdom, Biome

    def bounding_rect(self) -> QRectF:
        if not self.vertices:
            return QRectF()
        xs = [v.position.x() for v in self.vertices]
        ys = [v.position.y() for v in self.vertices]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def to_path(self) -> QPainterPath:
        path = QPainterPath()
        if len(self.vertices) < 2:
            return path
        path.moveTo(self.vertices[0].position)
        for i in range(1, len(self.vertices)):
            prev = self.vertices[i - 1]
            curr = self.vertices[i]
            if prev.control_out and curr.control_in:
                path.cubicTo(prev.control_out, curr.control_in, curr.position)
            elif prev.control_out:
                path.quadTo(prev.control_out, curr.position)
            elif curr.control_in:
                path.quadTo(curr.control_in, curr.position)
            else:
                path.lineTo(curr.position)
        if self.closed and len(self.vertices) > 2:
            last = self.vertices[-1]
            first = self.vertices[0]
            if last.control_out and first.control_in:
                path.cubicTo(last.control_out, first.control_in, first.position)
            elif last.control_out:
                path.quadTo(last.control_out, first.position)
            elif first.control_in:
                path.quadTo(first.control_in, first.position)
            else:
                path.lineTo(first.position)
            path.closeSubpath()
        return path

    def hit_test(self, point: QPointF, tolerance: float = 5.0) -> bool:
        path = self.to_path()
        if path.contains(point):
            return True
        stroker_path = QPainterPath()
        stroker_path.addPath(path)
        for v in self.vertices:
            if (v.position - point).manhattanLength() < tolerance:
                return True
        return False

    def find_vertex(self, point: QPointF, tolerance: float = 8.0) -> int:
        for i, v in enumerate(self.vertices):
            if (v.position - point).manhattanLength() < tolerance:
                return i
        return -1


# ─── Painting Engine ─────────────────────────────────────────────────────────

class PaintingEngine:
    def __init__(self):
        self._mode: PaintMode = PaintMode.PAINT
        self._strokes: list[PaintStroke] = []
        self._regions: dict[str, RegionPolygon] = {}
        self._active_stroke: Optional[PaintStroke] = None
        self._active_polygon: Optional[RegionPolygon] = None
        self._snap_enabled: bool = True
        self._snap_threshold: float = 10.0
        self._brush_size: float = 10.0
        self._brush_color: QColor = QColor(255, 255, 255)
        self._brush_opacity: float = 1.0
        self._brush_hardness: float = 0.8
        self._target_layer: Optional[str] = None

    # ─── Mode ────────────────────────────────────────────────────────────

    @property
    def mode(self) -> PaintMode:
        return self._mode

    def set_mode(self, mode: PaintMode):
        self._mode = mode

    # ─── Brush Config ────────────────────────────────────────────────────

    def set_brush(self, size: float = None, color: QColor = None,
                  opacity: float = None, hardness: float = None):
        if size is not None:
            self._brush_size = max(1.0, min(500.0, size))
        if color is not None:
            self._brush_color = color
        if opacity is not None:
            self._brush_opacity = max(0.0, min(1.0, opacity))
        if hardness is not None:
            self._brush_hardness = max(0.0, min(1.0, hardness))

    def set_target_layer(self, layer_id: Optional[str]):
        self._target_layer = layer_id

    # ─── Stroke Operations ───────────────────────────────────────────────

    def begin_stroke(self, point: QPointF) -> PaintStroke:
        self._active_stroke = PaintStroke(
            mode=self._mode,
            points=[point],
            color=QColor(self._brush_color),
            size=self._brush_size,
            opacity=self._brush_opacity,
            hardness=self._brush_hardness,
            target_layer=self._target_layer,
        )
        return self._active_stroke

    def add_point(self, point: QPointF):
        if self._active_stroke:
            self._active_stroke.points.append(point)

    def end_stroke(self) -> Optional[PaintStroke]:
        stroke = self._active_stroke
        if stroke and len(stroke.points) > 1:
            self._strokes.append(stroke)
        self._active_stroke = None
        return stroke

    # ─── Polygon Operations ──────────────────────────────────────────────

    def begin_polygon(self, point: QPointF) -> RegionPolygon:
        self._active_polygon = RegionPolygon(
            vertices=[Vertex(position=self._snap(point))],
            fill_color=QColor(self._brush_color),
            border_color=QColor(self._brush_color.lighter(150)),
        )
        return self._active_polygon

    def add_vertex(self, point: QPointF, control_in: QPointF = None,
                   control_out: QPointF = None):
        if not self._active_polygon:
            return
        snapped = self._snap(point)
        self._active_polygon.vertices.append(
            Vertex(position=snapped, control_in=control_in, control_out=control_out)
        )

    def close_polygon(self) -> Optional[RegionPolygon]:
        poly = self._active_polygon
        if poly and len(poly.vertices) >= 3:
            poly.closed = True
            self._regions[poly.id] = poly
        self._active_polygon = None
        return poly

    def cancel_polygon(self):
        self._active_polygon = None

    # ─── Region Management ───────────────────────────────────────────────

    def add_region(self, region: RegionPolygon):
        self._regions[region.id] = region

    def remove_region(self, region_id: str) -> Optional[RegionPolygon]:
        return self._regions.pop(region_id, None)

    def get_region(self, region_id: str) -> Optional[RegionPolygon]:
        return self._regions.get(region_id)

    def get_all_regions(self) -> list[RegionPolygon]:
        return list(self._regions.values())

    def find_region_at(self, point: QPointF) -> Optional[RegionPolygon]:
        for region in reversed(list(self._regions.values())):
            if region.hit_test(point):
                return region
        return None

    # ─── Vertex Editing ──────────────────────────────────────────────────

    def move_vertex(self, region_id: str, vertex_idx: int, new_pos: QPointF):
        region = self._regions.get(region_id)
        if region and 0 <= vertex_idx < len(region.vertices):
            region.vertices[vertex_idx].position = self._snap(new_pos)

    def set_bezier(self, region_id: str, vertex_idx: int,
                   control_in: QPointF = None, control_out: QPointF = None):
        region = self._regions.get(region_id)
        if region and 0 <= vertex_idx < len(region.vertices):
            region.vertices[vertex_idx].control_in = control_in
            region.vertices[vertex_idx].control_out = control_out

    def insert_vertex(self, region_id: str, after_idx: int, position: QPointF):
        region = self._regions.get(region_id)
        if region and 0 <= after_idx < len(region.vertices):
            region.vertices.insert(after_idx + 1, Vertex(position=self._snap(position)))

    def remove_vertex(self, region_id: str, vertex_idx: int):
        region = self._regions.get(region_id)
        if region and len(region.vertices) > 3 and 0 <= vertex_idx < len(region.vertices):
            region.vertices.pop(vertex_idx)

    # ─── Region Operations ───────────────────────────────────────────────

    def subdivide_region(self, region_id: str) -> list[RegionPolygon]:
        """Split region into two halves at midpoint."""
        region = self._regions.get(region_id)
        if not region or len(region.vertices) < 4:
            return []
        mid = len(region.vertices) // 2
        v1 = region.vertices[:mid + 1]
        v2 = region.vertices[mid:]
        r1 = RegionPolygon(name=f"{region.name}_A", vertices=v1,
                           fill_color=QColor(region.fill_color),
                           border_color=QColor(region.border_color),
                           entity_type=region.entity_type)
        r2 = RegionPolygon(name=f"{region.name}_B", vertices=v2,
                           fill_color=QColor(region.fill_color),
                           border_color=QColor(region.border_color),
                           entity_type=region.entity_type)
        self._regions.pop(region_id)
        self._regions[r1.id] = r1
        self._regions[r2.id] = r2
        return [r1, r2]

    def merge_regions(self, id_a: str, id_b: str) -> Optional[RegionPolygon]:
        """Merge two regions by combining vertices."""
        a = self._regions.get(id_a)
        b = self._regions.get(id_b)
        if not a or not b:
            return None
        merged = RegionPolygon(
            name=f"{a.name}+{b.name}",
            vertices=a.vertices + b.vertices,
            fill_color=QColor(a.fill_color),
            border_color=QColor(a.border_color),
            entity_type=a.entity_type,
        )
        self._regions.pop(id_a)
        self._regions.pop(id_b)
        self._regions[merged.id] = merged
        return merged

    def link_entity(self, region_id: str, entity_id: str, entity_type: str):
        region = self._regions.get(region_id)
        if region:
            region.entity_id = entity_id
            region.entity_type = entity_type

    # ─── Rendering ───────────────────────────────────────────────────────

    def render_region(self, painter: QPainter, region: RegionPolygon):
        path = region.to_path()
        if path.isEmpty():
            return
        painter.save()
        painter.setOpacity(region.opacity)
        # Fill
        if region.fill_type == FillType.GRADIENT:
            rect = region.bounding_rect()
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0, region.gradient_start)
            grad.setColorAt(1, region.gradient_end)
            painter.setBrush(QBrush(grad))
        elif region.fill_type == FillType.PATTERN:
            painter.setBrush(QBrush(region.fill_color, self._pattern_style(region.pattern)))
        else:
            painter.setBrush(QBrush(region.fill_color))
        # Border
        if region.border_width > 0:
            painter.setPen(QPen(region.border_color, region.border_width))
        else:
            painter.setPen(QPen(QColor(0, 0, 0, 0)))
        painter.drawPath(path)
        painter.restore()

    def render_all(self, painter: QPainter):
        for region in self._regions.values():
            self.render_region(painter, region)

    # ─── Snap ────────────────────────────────────────────────────────────

    def set_snap(self, enabled: bool, threshold: float = 10.0):
        self._snap_enabled = enabled
        self._snap_threshold = threshold

    def _snap(self, point: QPointF) -> QPointF:
        if not self._snap_enabled or not self._regions:
            return point
        closest = None
        min_dist = self._snap_threshold
        for region in self._regions.values():
            for v in region.vertices:
                dist = (v.position - point).manhattanLength()
                if dist < min_dist:
                    min_dist = dist
                    closest = v.position
        return QPointF(closest) if closest else point

    @staticmethod
    def _pattern_style(pattern: PatternType):
        from PySide6.QtCore import Qt
        mapping = {
            PatternType.HATCH: Qt.BDiagPattern,
            PatternType.DOTS: Qt.Dense6Pattern,
            PatternType.CROSS_HATCH: Qt.CrossPattern,
            PatternType.DIAGONAL: Qt.FDiagPattern,
        }
        return mapping.get(pattern, Qt.SolidPattern)

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def stroke_count(self) -> int:
        return len(self._strokes)

    @property
    def region_count(self) -> int:
        return len(self._regions)
