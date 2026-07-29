"""LightItem — an invisible-until-selected draggable handle for a map
light: no icon (the glow itself, painted by GlobalLightingOverlay — see
lighting_overlay.py — is the light's only visible representation), just a
thin dashed outline hinting at its radius/cone while selected, so it can
still be picked out and edited without reading as a stamped lightbulb badge
sitting on top of the map. Custom-painted for the same reason as MarkerItem
(see that module's docstring) rather than a QGraphicsPixmapItem.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyle

from src.canvas.item_utils import enable_hover_glow
from src.engines.light import LightProperties
from src.engines.lighting_compositor import cone_path

_HOVER_PAD = 6.0


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
        # Sized to the full radius (not just the icon) so the dashed range
        # gizmo drawn on selection is never clipped by the item's own bounds.
        r = max(4.0, self.props.radius) + _HOVER_PAD
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter, option, widget=None):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        if selected or self._hovered:
            self._draw_range_gizmo(painter)

    def _draw_range_gizmo(self, painter):
        """Thin dashed outline of the light's reach while selected — a
        reference for editing (like Blender's lamp viewport gizmo), not the
        light itself (GlobalLightingOverlay renders the actual glow)."""
        radius = max(4.0, self.props.radius)
        color = QColor(self.props.color)
        color.setAlpha(140)
        painter.save()
        painter.setPen(QPen(color, 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.props.light_type == "spot":
            painter.drawPath(cone_path(radius, self.props.direction_deg, self.props.cone_angle_deg))
        else:
            painter.drawEllipse(QPointF(0, 0), radius, radius)
        painter.restore()
