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
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyle

from src.canvas.item_utils import enable_hover_glow
from src.engines.light import LightProperties
from src.engines.lighting_compositor import cone_path

_HOVER_PAD = 6.0
# Fixed-size clickable "hotspot" around the light's own position — NOT
# related to props.radius (how far the light reaches). Without a shape()
# override, Qt's default hit-test falls back to boundingRect() (the WHOLE
# radius square, mostly empty/invisible space), so clicking anywhere in a
# light's reach — even squarely on an unrelated mob/asset sitting well
# within that radius — would claim the click over whatever's actually
# drawn there. This keeps the light selectable only near where it visibly
# is (or would be, via its dashed gizmo), same idea as a marker's icon
# hotspot.
_CLICK_RADIUS = 16.0


class LightItem(QGraphicsItem):
    """Local (0, 0) is the light's own position — same convention as
    MarkerItem/TextItem so selection/drag/rotate handles behave the same."""

    # Bound once by LightMediator right after it creates the single
    # GlobalLightingOverlay (see bind_overlay()) — lets every LightItem,
    # however it was constructed (placed fresh via LightTool or loaded from
    # the DB), notify the overlay the instant it moves instead of the
    # overlay only finding out up to _REFRESH_TICK_MS later via blind
    # polling.
    _overlay = None

    def __init__(self, props: LightProperties | None = None, parent=None):
        super().__init__(parent)
        self.props = props or LightProperties()
        self._hovered = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setData(0, {"item_type": "light"})
        enable_hover_glow(self, self._on_hover)

    @classmethod
    def bind_overlay(cls, overlay):
        cls._overlay = overlay

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and LightItem._overlay is not None:
            LightItem._overlay.notify_light_moved(self)
        return super().itemChange(change, value)

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

    def shape(self) -> QPainterPath:
        """Overrides the default (boundingRect()-derived, i.e. the whole
        radius square) hit-test shape with a small fixed-size circle at the
        light's own position — see _CLICK_RADIUS. An already-selected
        light can still be grabbed by clicking anywhere within its drawn
        gizmo/cone via ItemInteraction.pos_in_selection_bounds' own
        fallback (which uses selection_bounding_rect(), not this), so
        narrowing this doesn't break dragging an already-selected light —
        only what a fresh click, with something else in the way, resolves
        to."""
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), _CLICK_RADIUS, _CLICK_RADIUS)
        return path

    def selection_bounding_rect(self) -> QRectF:
        """Tight local bounds of what's actually drawn — read by
        TransformEngine._item_bounds (same mechanism TextItem uses to keep
        its selection border from including its generous hover-margin
        boundingRect()). A "spot" light's cone only fills a wedge of its
        full boundingRect() (a symmetric square sized for the worst case:
        rotating the cone to face any direction, or a non-spot light's
        full circle) — without this override the selection box always
        centered a big empty square around the light instead of hugging
        the cone, most visibly for a narrow cone_angle_deg pointing off to
        one side."""
        radius = max(4.0, self.props.radius)
        if self.props.light_type == "spot":
            return cone_path(radius, self.props.direction_deg, self.props.cone_angle_deg).boundingRect()
        return QRectF(-radius, -radius, radius * 2, radius * 2)

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
