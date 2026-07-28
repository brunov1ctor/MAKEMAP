"""LightItem — a real map light object: a radial glow (radius/color/
intensity), optionally with a projected shadow silhouette cut out where an
asset stamp (a building/prop) blocks it, and optional animated "volumetric"
beams. Custom-painted, same reasoning as MarkerItem (see marker_item.py's
module docstring) for why this isn't a QGraphicsPixmapItem.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QBrush, QFont, QPainterPath, QPolygonF, QRadialGradient,
    QLinearGradient,
)
from PySide6.QtWidgets import QGraphicsItem, QStyle

from src.canvas.item_utils import enable_hover_glow
from src.engines.light import LightProperties, light_icon

_HOVER_PAD = 6.0
_ICON_SIZE = 22.0


class LightItem(QGraphicsItem):
    """Local (0, 0) is the light's own position — same convention as
    MarkerItem/TextItem so selection/drag/rotate handles behave the same."""

    def __init__(self, props: LightProperties | None = None, parent=None):
        super().__init__(parent)
        self.props = props or LightProperties()
        self._hovered = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setData(0, {"item_type": "light"})
        enable_hover_glow(self, self._on_hover)

    def _on_hover(self, hovered: bool):
        # Deliberately doesn't setScale()/apply a drop-shadow like the mob
        # stamp's hover does — scaling the whole item would visually change
        # the light's radius, which is a real configured property, not a
        # cosmetic size. Only the center icon glyph reacts to hover.
        self._hovered = hovered
        self.update()

    def boundingRect(self) -> QRectF:
        r = max(4.0, self.props.radius) + _HOVER_PAD
        return QRectF(-r, -r, r * 2, r * 2)

    # ─── Shadow casting ─────────────────────────────────────────────────
    # Classic 2D "visibility polygon" technique: the lit area is the full
    # light disc minus one shadow quad per occluder in range. Recomputed
    # fresh every paint() (no cached state) — LightMediator's timer just
    # has to call update() periodically so moving occluders stay in sync.

    @staticmethod
    def _shadow_quad(corners: list[QPointF], radius: float) -> QPolygonF | None:
        """corners: an occluder's 4 corners in the light's local space
        (light at origin). Returns the quad silhouette-shadow polygon cast
        away from the origin out to `radius`, or None if the corners are
        degenerate (occluder sits exactly on the light)."""
        angles = [math.atan2(c.y(), c.x()) for c in corners]
        # Circular mean avoids picking the wrong "extremes" when the
        # occluder straddles the atan2 +-pi discontinuity.
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

    def _occluder_rects(self, scene_pos: QPointF, radius: float):
        if self.scene() is None:
            return
        search = QRectF(scene_pos.x() - radius, scene_pos.y() - radius, radius * 2, radius * 2)
        for other in self.scene().items(search):
            if other is self:
                continue
            data = other.data(0)
            if not isinstance(data, dict) or data.get("item_type") != "asset":
                continue
            yield other.sceneBoundingRect()

    def _compute_lit_path(self, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), radius, radius)
        if not self.props.shadows:
            return path

        scene_pos = self.scenePos()
        for srect in self._occluder_rects(scene_pos, radius):
            corners = [
                QPointF(srect.left() - scene_pos.x(), srect.top() - scene_pos.y()),
                QPointF(srect.right() - scene_pos.x(), srect.top() - scene_pos.y()),
                QPointF(srect.right() - scene_pos.x(), srect.bottom() - scene_pos.y()),
                QPointF(srect.left() - scene_pos.x(), srect.bottom() - scene_pos.y()),
            ]
            if min(math.hypot(c.x(), c.y()) for c in corners) > radius:
                continue
            quad = self._shadow_quad(corners, radius)
            if quad is None:
                continue
            shadow_path = QPainterPath()
            shadow_path.addPolygon(quad)
            shadow_path.closeSubpath()
            path = path.subtracted(shadow_path)
        return path

    # ─── Painting ───────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        radius = max(4.0, self.props.radius)
        lit_path = self._compute_lit_path(radius)

        color = QColor(self.props.color)
        alpha = max(0, min(255, int(210 * self.props.intensity)))
        c_in, c_out = QColor(color), QColor(color)
        c_in.setAlpha(alpha)
        c_out.setAlpha(0)
        grad = QRadialGradient(0, 0, radius)
        grad.setColorAt(0.0, c_in)
        grad.setColorAt(1.0, c_out)

        painter.save()
        painter.setClipPath(lit_path)
        painter.fillPath(lit_path, QBrush(grad))
        if self.props.volumetric:
            self._draw_volumetric(painter, radius)
        painter.restore()

        size = _ICON_SIZE * (1.15 if self._hovered else 1.0)
        painter.setPen(QColor(255, 255, 255, 235 if self._hovered else 190))
        font = QFont()
        font.setPointSizeF(size * 0.6)
        painter.setFont(font)
        painter.drawText(
            QRectF(-size / 2, -size / 2, size, size),
            Qt.AlignmentFlag.AlignCenter, light_icon(self.props.light_type),
        )

    def _draw_volumetric(self, painter, radius: float):
        """Soft rotating beams within the lit area — a visual flourish,
        not a real fog/volumetric-scattering simulation. Stateless (driven
        by time.monotonic()), same technique as the Marcador shaders."""
        phase = time.monotonic()
        n = 4
        beam_width = radius * 0.16
        for i in range(n):
            ang = math.degrees(phase * 12 + i * (360 / n))
            painter.save()
            painter.rotate(ang)
            grad = QLinearGradient(0, 0, radius, 0)
            grad.setColorAt(0.0, QColor(255, 255, 255, 55))
            grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPolygon(QPolygonF([
                QPointF(0, -beam_width / 2), QPointF(radius, -beam_width / 4),
                QPointF(radius, beam_width / 4), QPointF(0, beam_width / 2),
            ]))
            painter.restore()
