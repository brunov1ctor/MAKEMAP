"""Shared lighting math — occluder shadow projection, spot-cone shape, and
falloff-gradient computation. Extracted from the old LightItem.paint() so
both the on-canvas light gizmo (light_item.py, just draws a selection
outline hint) and the whole-map GlobalLightingOverlay (lighting_overlay.py,
does the actual illumination) compute identical shadows/falloff instead of
duplicating the math.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPolygonF, QRadialGradient


def shadow_quad(corners: list[QPointF], radius: float) -> QPolygonF | None:
    """corners: an occluder's 4 corners in the light's local space (light at
    origin). Returns the quad silhouette-shadow polygon cast away from the
    origin out to `radius` — the closer the occluder sits to the origin, the
    more of `radius` is left to project across, so the shadow is naturally
    longer for occluders near the light and shorter for occluders near the
    edge of its reach ("proximity" shadow length). Returns None if the
    corners are degenerate (occluder sits exactly on the light)."""
    angles = [math.atan2(c.y(), c.x()) for c in corners]
    # Circular mean avoids picking the wrong "extremes" when the occluder
    # straddles the atan2 +-pi discontinuity.
    mean_ang = math.atan2(
        sum(math.sin(a) for a in angles) / len(angles),
        sum(math.cos(a) for a in angles) / len(angles),
    )

    def rel(a: float) -> float:
        d = a - mean_ang
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        return d

    rels = [rel(a) for a in angles]
    c1 = corners[rels.index(min(rels))]
    c2 = corners[rels.index(max(rels))]

    def extend(c: QPointF) -> QPointF | None:
        d = math.hypot(c.x(), c.y())
        if d < 1e-6:
            return None
        scale = radius / d
        return QPointF(c.x() * scale, c.y() * scale)

    f1, f2 = extend(c1), extend(c2)
    if f1 is None or f2 is None:
        return None
    return QPolygonF([c1, f1, f2, c2])


def occluder_rects(scene, origin: QPointF, radius: float, exclude=None):
    """Scene-space bounding rects of every asset stamp (a house, a prop —
    anything BrushTool.place_stamp_item tagged item_type == 'asset') within
    `radius` of `origin`. This is how a stamped house is already recognized
    as a shadow occluder."""
    if scene is None:
        return
    search = QRectF(origin.x() - radius, origin.y() - radius, radius * 2, radius * 2)
    for other in scene.items(search):
        if other is exclude:
            continue
        data = other.data(0)
        if not isinstance(data, dict) or data.get("item_type") != "asset":
            continue
        yield other.sceneBoundingRect()


def cone_path(radius: float, direction_deg: float, cone_angle_deg: float) -> QPainterPath:
    """Pie-slice in LOCAL coordinates (apex at (0, 0)) aimed at
    `direction_deg`, `cone_angle_deg` wide — the lit shape of a spot light."""
    path = QPainterPath()
    path.moveTo(0, 0)
    half = max(1.0, cone_angle_deg) / 2.0
    path.arcTo(QRectF(-radius, -radius, radius * 2, radius * 2), -direction_deg - half, cone_angle_deg)
    path.closeSubpath()
    return path


def compute_lit_path(
    scene, origin: QPointF, radius: float, *, light_type: str = "point",
    direction_deg: float = 0.0, cone_angle_deg: float = 45.0,
    shadows: bool = True, exclude=None,
) -> QPainterPath:
    """Lit-area path in LOCAL coordinates (light at (0, 0)) — a full disc
    for point/sky/fog, or a cone for spot — minus one shadow quad per
    occluder asset in range."""
    if light_type == "spot":
        path = cone_path(radius, direction_deg, cone_angle_deg)
    else:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), radius, radius)

    if not shadows:
        return path

    for srect in occluder_rects(scene, origin, radius, exclude=exclude):
        corners = [
            QPointF(srect.left() - origin.x(), srect.top() - origin.y()),
            QPointF(srect.right() - origin.x(), srect.top() - origin.y()),
            QPointF(srect.right() - origin.x(), srect.bottom() - origin.y()),
            QPointF(srect.left() - origin.x(), srect.bottom() - origin.y()),
        ]
        if min(math.hypot(c.x(), c.y()) for c in corners) > radius:
            continue
        quad = shadow_quad(corners, radius)
        if quad is None:
            continue
        shadow_path = QPainterPath()
        shadow_path.addPolygon(quad)
        shadow_path.closeSubpath()
        path = path.subtracted(shadow_path)
    return path


def falloff_gradient(color: QColor, intensity: float, radius: float) -> QRadialGradient:
    """Smooth falloff instead of a flat linear ramp to zero — alpha is
    already near-zero well before the outer edge of `radius`, so the lit
    area blends into the map instead of reading as a hard-edged stamped
    disc (the original complaint driving this whole module's existence)."""
    alpha_peak = max(0, min(255, int(210 * intensity)))
    grad = QRadialGradient(0, 0, radius)
    for stop, factor in ((0.0, 1.0), (0.35, 0.85), (0.7, 0.45), (1.0, 0.0)):
        c = QColor(color)
        c.setAlpha(int(alpha_peak * factor))
        grad.setColorAt(stop, c)
    return grad
