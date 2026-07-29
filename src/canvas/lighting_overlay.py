"""GlobalLightingOverlay — a single whole-scene QGraphicsItem with two
layers: an optional whole-map day/night darkening tint (see set_sky/
_paint_sky, driven by the single global "sky" setting — GLOBAL_TYPES in
src/engines/light.py), painted first, then every LightItem's glow on top
with CompositionMode_Plus (additive) so overlapping lights actually add up
into brighter light instead of stacking as separate translucent decals and
so placed lights visibly "cut through" the night tint. Each light's own
occluder shadow is subtracted from its glow before painting (see
lighting_compositor), so a stamped house still blocks light exactly like
before. LightMediator owns creating this and ticking its refresh in sync
with moving lights/occluders/the sky setting.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QGraphicsItem

from src.canvas.light_item import LightItem
from src.engines.light import LightProperties
from src.engines.lighting_compositor import compute_lit_path, cone_path, falloff_gradient

# Extra reach past each light's own radius so the overlay's bounding rect
# comfortably contains the soft falloff tail (falloff_gradient's alpha is
# already ~0 near the edge, but Qt still needs the geometry to cover it).
_MARGIN = 32.0


class GlobalLightingOverlay(QGraphicsItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(8)  # above terrain/objects, below light gizmos (z=9)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._sky: LightProperties | None = None

    def set_sky(self, props: LightProperties | None):
        """LightMediator calls this whenever the global sky setting loads or
        changes. day_amount >= 100 (full day) is treated as "off" so a fresh
        map with no sky configured yet costs nothing extra to paint."""
        self._sky = props

    def _sky_active(self) -> bool:
        return self._sky is not None and self._sky.day_amount < 100.0

    def _lights(self) -> list[LightItem]:
        if self.scene() is None:
            return []
        return [it for it in self.scene().items() if isinstance(it, LightItem) and it.isVisible()]

    def boundingRect(self) -> QRectF:
        lights = self._lights()
        sky_active = self._sky_active()
        if not lights and not sky_active:
            return QRectF()
        # The sky tint covers the whole map, not just the area around
        # placed lights — the scene's own (fixed, huge) sceneRect is the
        # simplest stand-in for "the whole map" without threading a
        # MapBoundary reference through (Qt clips actual painting to
        # whatever's exposed on screen, so this costs nothing extra).
        rect = self.scene().sceneRect() if sky_active and self.scene() else None
        for light in lights:
            r = max(4.0, light.props.radius) + _MARGIN
            pos = light.scenePos()
            lr = QRectF(pos.x() - r, pos.y() - r, r * 2, r * 2)
            rect = lr if rect is None else rect.united(lr)
        return rect if rect is not None else QRectF()

    def paint(self, painter: QPainter, option, widget=None):
        lights = self._lights()
        sky_active = self._sky_active()
        if not lights and not sky_active:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if sky_active:
            self._paint_sky(painter, option)
        if lights:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            for light in lights:
                self._paint_light(painter, light)
            painter.restore()

    def _paint_sky(self, painter: QPainter, option):
        t = max(0.0, min(100.0, self._sky.day_amount)) / 100.0  # 1 = day, 0 = night
        alpha = int(225 * (1.0 - t))
        if alpha <= 0:
            return
        color = QColor(self._sky.color)
        color.setAlpha(alpha)
        # Only the actually-exposed (on-screen) area needs filling — the
        # item's own boundingRect is the whole map, but Qt hands paint()
        # the real redraw region via option.exposedRect.
        painter.fillRect(option.exposedRect, color)

    def _paint_light(self, painter: QPainter, light: LightItem):
        props = light.props
        radius = max(4.0, props.radius)
        origin = light.scenePos()
        lit_path = compute_lit_path(
            self.scene(), origin, radius, light_type=props.light_type,
            direction_deg=props.direction_deg, cone_angle_deg=props.cone_angle_deg,
            shadows=props.shadows, exclude=light,
        )
        painter.save()
        painter.translate(origin)
        painter.setClipPath(lit_path)
        painter.fillPath(lit_path, QBrush(falloff_gradient(QColor(props.color), props.intensity, radius)))
        if props.volumetric:
            self._draw_volumetric(painter, radius)
        painter.restore()

    def _draw_volumetric(self, painter: QPainter, radius: float):
        """Soft rotating beams within the lit area — a visual flourish, not
        a real fog/volumetric-scattering simulation. Stateless (driven by
        time.monotonic()), same technique the old LightItem used."""
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


class LightGhostItem(QGraphicsItem):
    """Cursor-following preview of the light about to be placed — while
    LightTool is armed (a type was picked in LightPanel but nothing's been
    clicked on the map yet), this follows the mouse showing just the glow
    (no icon, no occluder shadows — there's no real light/position yet) so
    the user can see roughly where/how big it'll land before committing.
    LightTool owns creating/moving/removing this; it's never persisted."""

    def __init__(self, props: LightProperties, parent=None):
        super().__init__(parent)
        self.props = props
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setZValue(9999)  # always on top so it reads clearly as a cursor-following ghost

    def boundingRect(self) -> QRectF:
        r = max(4.0, self.props.radius) + 4.0
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None):
        radius = max(4.0, self.props.radius)
        if self.props.light_type == "spot":
            path = cone_path(radius, self.props.direction_deg, self.props.cone_angle_deg)
        else:
            path = QPainterPath()
            path.addEllipse(QPointF(0, 0), radius, radius)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setClipPath(path)
        painter.fillPath(path, QBrush(falloff_gradient(QColor(self.props.color), self.props.intensity, radius)))
        painter.restore()
