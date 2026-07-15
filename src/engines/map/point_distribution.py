"""Point distribution algorithms for procedural generation."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPolygonF


def generate_points_in_polygon(
    polygon: QPolygonF,
    count: int,
    min_distance: float,
    seed: int = 0,
) -> list[QPointF]:
    """Generate well-spaced random points inside a polygon.

    Uses rejection sampling with minimum distance constraint.
    """
    rng = random.Random(seed)
    bounds = polygon.boundingRect()
    points: list[QPointF] = []
    max_attempts = count * 30

    for _ in range(max_attempts):
        if len(points) >= count:
            break

        point = QPointF(
            rng.uniform(bounds.left(), bounds.right()),
            rng.uniform(bounds.top(), bounds.bottom()),
        )

        if not polygon.containsPoint(point, Qt.FillRule.OddEvenFill):
            continue

        too_close = any(
            math.hypot(point.x() - p.x(), point.y() - p.y()) < min_distance
            for p in points
        )

        if not too_close:
            points.append(point)

    return points


def distance_to_polygon_edge(point: QPointF, polygon: QPolygonF) -> float:
    """Approximate distance from point to nearest polygon edge."""
    min_dist = float("inf")
    count = polygon.count()

    for i in range(count):
        a = polygon.at(i)
        b = polygon.at((i + 1) % count)
        dist = _point_to_segment_distance(point, a, b)
        if dist < min_dist:
            min_dist = dist

    return min_dist


def _point_to_segment_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Distance from point p to line segment a-b."""
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    length_sq = dx * dx + dy * dy

    if length_sq < 1e-10:
        return math.hypot(p.x() - a.x(), p.y() - a.y())

    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length_sq))
    proj_x = a.x() + t * dx
    proj_y = a.y() + t * dy
    return math.hypot(p.x() - proj_x, p.y() - proj_y)
