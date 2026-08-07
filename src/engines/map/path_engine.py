"""Shared base for path-like map elements (roads, rivers, ...): a polyline/
bezier path made of points, with hit-testing, CRUD, snapping and rendering
plumbing common to all of them. Concrete engines (RoadEngine, RiverEngine)
add only their own domain-specific behavior (bridges vs. confluences, etc)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPen, Qt


@dataclass
class PathPoint:
    position: QPointF
    control_in: Optional[QPointF] = None
    control_out: Optional[QPointF] = None
    width: float = 12.0


@dataclass
class PathElement:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    points: list = field(default_factory=list)
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

    def hit_test(self, point: QPointF, tolerance: float = None,
                 sample_step: int = 5) -> bool:
        if not self.points:
            return False
        path = self.to_center_path()
        max_w = max(p.width for p in self.points) / 2
        tol = tolerance if tolerance else max_w + 4
        if not self.bounding_rect().adjusted(-tol, -tol, tol, tol).contains(point):
            return False
        for p in self.points:
            if (p.position - point).manhattanLength() < tol:
                return True
        for t in range(0, 101, sample_step):
            pt = path.pointAtPercent(t / 100.0)
            if (pt - point).manhattanLength() < tol:
                return True
        return False

    def find_point(self, pos: QPointF, tolerance: float = 10.0) -> int:
        for i, p in enumerate(self.points):
            if (p.position - pos).manhattanLength() < tolerance:
                return i
        return -1


TElement = TypeVar("TElement", bound=PathElement)


class PathEngine(Generic[TElement]):
    """Generic CRUD/snap/render plumbing over a dict of PathElement.
    Subclasses pick an element class and expose domain-named methods
    (begin_road/begin_river, ...) that delegate to the underscored
    generics here."""

    def __init__(self, default_snap_threshold: float = 12.0):
        self._items: dict[str, TElement] = {}
        self._active: Optional[TElement] = None
        self._snap_enabled: bool = True
        self._snap_threshold: float = default_snap_threshold

    # ─── CRUD ────────────────────────────────────────────────────────────

    def _add(self, item: TElement):
        self._items[item.id] = item

    def _remove(self, item_id: str) -> Optional[TElement]:
        return self._items.pop(item_id, None)

    def _get(self, item_id: str) -> Optional[TElement]:
        return self._items.get(item_id)

    def _get_all(self) -> list:
        return list(self._items.values())

    def _find_at(self, point: QPointF) -> Optional[TElement]:
        for item in reversed(list(self._items.values())):
            if item.hit_test(point):
                return item
        return None

    # ─── Point editing ───────────────────────────────────────────────────

    def move_point(self, item_id: str, idx: int, new_pos: QPointF):
        item = self._items.get(item_id)
        if item and 0 <= idx < len(item.points):
            item.points[idx].position = self._snap(new_pos)

    def set_point_attr(self, item_id: str, idx: int, attr: str, value: float,
                        lo: float = 0.0, hi: float = float("inf")):
        item = self._items.get(item_id)
        if item and 0 <= idx < len(item.points):
            setattr(item.points[idx], attr, max(lo, min(hi, value)))

    def insert_point(self, item_id: str, after_idx: int, position: QPointF,
                      **extra_fields):
        item = self._items.get(item_id)
        if item and 0 <= after_idx < len(item.points):
            prev = item.points[after_idx]
            point_cls = type(prev)
            item.points.insert(after_idx + 1, point_cls(
                position=self._snap(position), width=prev.width, **extra_fields))

    def remove_point(self, item_id: str, idx: int):
        item = self._items.get(item_id)
        if item and len(item.points) > 2 and 0 <= idx < len(item.points):
            item.points.pop(idx)

    # ─── Rendering ───────────────────────────────────────────────────────

    def render_all(self, painter: QPainter, render_one):
        for item in self._items.values():
            render_one(painter, item)

    @staticmethod
    def _stroke_path(painter: QPainter, path: QPainterPath, color, width: float,
                      dash_pattern: list[float] = None):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if dash_pattern:
            pen.setDashPattern(dash_pattern)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    # ─── Snap ────────────────────────────────────────────────────────────

    def set_snap(self, enabled: bool, threshold: float = None):
        self._snap_enabled = enabled
        if threshold is not None:
            self._snap_threshold = threshold

    def _snap(self, point: QPointF) -> QPointF:
        if not self._snap_enabled or not self._items:
            return point
        closest = None
        min_dist = self._snap_threshold
        for item in self._items.values():
            for p in item.points:
                dist = (p.position - point).manhattanLength()
                if dist < min_dist:
                    min_dist = dist
                    closest = p.position
        return QPointF(closest) if closest else point

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._items)
