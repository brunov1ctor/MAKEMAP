"""Viewport — custom QGraphicsView with zoom, pan, and camera management."""

from __future__ import annotations

import math

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QPropertyAnimation, QEasingCurve, QTimer, QElapsedTimer
from PySide6.QtGui import (
    QWheelEvent, QMouseEvent, QKeyEvent, QPainter, QColor, QTransform, QPixmap, QImage,
    QLinearGradient,
)

from src.styles.tokens import Colors, Navigation


def _build_faded_pixmap(pixmap: QPixmap, fade_frac: float = 0.15) -> QPixmap:
    """A copy of `pixmap` with its left/right edges fading to transparent —
    used for tile_mode="fade", so overlapping tile copies blend instead of
    meeting at a hard seam."""
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, pixmap)
    gradient = QLinearGradient(0, 0, pixmap.width(), 0)
    gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
    gradient.setColorAt(min(0.5, fade_frac), QColor(0, 0, 0, 255))
    gradient.setColorAt(max(0.5, 1.0 - fade_frac), QColor(0, 0, 0, 255))
    gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.fillRect(result.rect(), gradient)
    painter.end()
    return result


def _apply_tint(pixmap: QPixmap, params: dict) -> QPixmap:
    strength = max(0.0, min(1.0, float(params.get("strength", 0.3))))
    if strength <= 0:
        return pixmap
    result = QPixmap(pixmap)
    painter = QPainter(result)
    # SourceAtop only paints where the destination is already opaque, so a
    # transparent-background layer image stays transparent instead of the
    # tint filling in its whole bounding rect.
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    tint = QColor(params.get("color", "#4FC3F7"))
    tint.setAlphaF(strength)
    painter.fillRect(result.rect(), tint)
    painter.end()
    return result


def _apply_blur(pixmap: QPixmap, params: dict) -> QPixmap:
    """Cheap approximate blur (downscale + smooth upscale) — good enough for
    a background layer and far cheaper than a real convolution per frame."""
    radius = max(0.0, float(params.get("radius", 4.0)))
    if radius < 1.0:
        return pixmap
    factor = max(1, int(radius))
    w, h = pixmap.width(), pixmap.height()
    small = pixmap.scaled(
        max(1, w // factor), max(1, h // factor),
        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    return small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _apply_chromatic(pixmap: QPixmap, params: dict) -> QPixmap:
    """Fakes chromatic aberration by ghosting two offset copies with additive
    blending under the sharp original — not a true per-channel split, but
    visually close and far cheaper."""
    offset = float(params.get("offset_px", 2.0))
    if offset <= 0:
        return pixmap
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.setOpacity(0.5)
    painter.drawPixmap(QPointF(-offset, 0), pixmap)
    painter.drawPixmap(QPointF(offset, 0), pixmap)
    painter.setOpacity(1.0)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


# "wave" isn't here — it's time-animated (needs `t`), so it's re-applied
# every frame in _draw_waved_pixmap instead of being pre-baked once like
# these three.
_STATIC_EFFECT_RENDERERS = {
    "tint": _apply_tint,
    "blur": _apply_blur,
    "chromatic": _apply_chromatic,
}


def _draw_waved_pixmap(painter: QPainter, dest_rect: QRectF, pixmap: QPixmap, t: float, params: dict):
    """Slices `pixmap` into horizontal strips and offsets each sideways by a
    sine wave — a cheap way to fake water/heat-haze distortion without a
    real per-pixel shader."""
    amplitude = float(params.get("amplitude", 6.0))
    frequency = float(params.get("frequency", 0.05))
    speed = float(params.get("speed", 1.0))
    if amplitude <= 0 or pixmap.height() <= 0:
        painter.drawPixmap(dest_rect.toRect(), pixmap)
        return
    sy = dest_rect.height() / pixmap.height()
    src_strip_h = max(1, int(pixmap.height() / 60))  # ~60 strips top to bottom
    dest_y = dest_rect.top()
    src_y = 0
    while src_y < pixmap.height():
        h = min(src_strip_h, pixmap.height() - src_y)
        dx = amplitude * math.sin(src_y * frequency + t * speed)
        dest_h = h * sy
        painter.drawPixmap(
            QRectF(dest_rect.left() + dx, dest_y, dest_rect.width(), dest_h),
            pixmap, QRectF(0, src_y, pixmap.width(), h),
        )
        dest_y += dest_h
        src_y += h


class _ParallaxRenderLayer:
    """Cached render data for one parallax layer — the mirrored/faded tile
    variants, and any static (tint/blur/chromatic) effects, are built once
    here (when the preset is applied), not per frame, since they're the
    same until the layer's image/tile_mode/effects change again. "wave" is
    the one effect kept separate (see wave_params) since it animates and
    has to be re-applied every frame."""

    def __init__(self, layer, pixmap: QPixmap):
        self.layer = layer
        processed = pixmap
        for effect in layer.effects:
            if not effect.enabled or effect.kind == "wave":
                continue
            renderer = _STATIC_EFFECT_RENDERERS.get(effect.kind)
            if renderer:
                processed = renderer(processed, effect.params)
        self.pixmap = processed
        self.mirrored = processed.transformed(QTransform().scale(-1, 1)) if layer.tile_mode == "mirror" else None
        self.faded = _build_faded_pixmap(processed) if layer.tile_mode == "fade" else None
        # Only the first enabled "wave" effect is applied — stacking two
        # wave distortions isn't worth the extra complexity for a
        # background effect.
        wave_effect = next((e for e in layer.effects if e.enabled and e.kind == "wave"), None)
        self.wave_params = wave_effect.params if wave_effect else None


class Viewport(QGraphicsView):
    """Main canvas viewport with infinite zoom and pan."""

    zoom_changed = Signal(float)  # emits current zoom level (1.0 = 100%)
    rotation_changed = Signal(float)  # emits current rotation, degrees [0, 360)
    cursor_moved = Signal(float, float)  # scene X, Y
    view_changed = Signal()  # emitted on any pan or zoom

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(QRectF(-5_000_000, -5_000_000, 10_000_000, 10_000_000))
        self.setScene(self._scene)

        # Rendering
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
        )

        # Appearance
        self.setBackgroundBrush(QColor(Colors.BG_SECONDARY))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Enable mouse tracking so mouseMoveEvent fires without button press
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # State
        self._zoom = 1.0
        self._rotation_deg = 0.0
        self._panning = False
        self._pan_start = QPointF()
        self._space_held = False
        self._bg_color: QColor | None = None
        self._bg_pixmap: QPixmap | None = None
        # _ParallaxRenderLayer list, back-to-front order — see
        # set_parallax_layers(). Empty = no parallax, fall back to
        # _bg_pixmap/_bg_color as before.
        self._parallax_pixmaps: list[_ParallaxRenderLayer] = []
        # Only ticks while at least one active layer needs continuous
        # redraws (orbit motion or any pulse) — plain pan-driven scroll
        # layers never need this, so the common case costs nothing.
        self._parallax_clock = QElapsedTimer()
        self._parallax_timer: QTimer | None = None

    # --- Background ---

    def set_background(self, color: QColor | None, pixmap: QPixmap | None):
        """Set a solid color or scaled image as the viewport background."""
        self._parallax_pixmaps = []
        self._bg_color = color
        self._bg_pixmap = pixmap
        if color and not pixmap:
            self.setBackgroundBrush(color)
        elif not color and not pixmap:
            self.setBackgroundBrush(QColor(Colors.BG_SECONDARY))
        else:
            # Use transparent brush so drawBackground handles it
            self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.viewport().update()

    def set_parallax_layers(self, layers: list) -> None:
        """Parallax background — several image layers scrolling at their
        own speed as the camera pans, for a sense of depth. `layers` is a
        list of ParallaxLayer (src.engines.map.parallax); speed_x/speed_y 0
        keeps a layer fixed to the screen on that axis (skybox-like), 1
        scrolls with the scene at the same rate as a normal static
        background image, and negative values drift the opposite way."""
        self._bg_color = None
        self._bg_pixmap = None
        self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        ordered = sorted(layers, key=lambda l: l.order)
        self._parallax_pixmaps = [
            _ParallaxRenderLayer(layer, QPixmap(layer.image_path)) for layer in ordered
        ]

        needs_clock = any(
            l.motion_mode == "orbit" or l.opacity_pulse or l.scale_pulse or l.rotation_pulse
            or any(e.enabled and e.kind == "wave" for e in l.effects)
            for l in layers
        )
        if needs_clock:
            if self._parallax_timer is None:
                self._parallax_timer = QTimer(self)
                self._parallax_timer.timeout.connect(self.viewport().update)
            self._parallax_clock.restart()
            self._parallax_timer.start(33)  # ~30fps
        elif self._parallax_timer is not None:
            self._parallax_timer.stop()

        self.viewport().update()

    def clear_parallax(self):
        self._parallax_pixmaps = []
        if self._parallax_timer is not None:
            self._parallax_timer.stop()
        self.viewport().update()

    def _parallax_time(self) -> float:
        return self._parallax_clock.elapsed() / 1000.0 if self._parallax_clock.isValid() else 0.0

    def _draw_parallax_layer(self, painter: QPainter, view_rect: QRectF,
                              tile_w: float, tile_h: float, render_layer: "_ParallaxRenderLayer", t: float):
        layer = render_layer.layer
        if render_layer.pixmap.isNull():
            return

        opacity = layer.opacity
        if layer.opacity_pulse and layer.opacity_period > 0:
            phase = (t / layer.opacity_period) * 2 * math.pi + layer.phase_offset
            mix = (math.sin(phase) + 1) / 2
            # opacity_min/max are a fraction OF the layer's base opacity, not
            # an absolute replacement — so lowering "Opac." still darkens the
            # layer even while the pulse is running, instead of the pulse
            # silently overriding it.
            pulse_factor = layer.opacity_min + (layer.opacity_max - layer.opacity_min) * mix
            opacity = layer.opacity * pulse_factor

        scale = 1.0
        if layer.scale_pulse and layer.scale_period > 0:
            phase = (t / layer.scale_period) * 2 * math.pi + layer.phase_offset
            mix = (math.sin(phase) + 1) / 2
            scale = (layer.scale_min + (layer.scale_max - layer.scale_min) * mix) / 100.0

        rotation = 0.0
        if layer.rotation_pulse and layer.rotation_period > 0:
            phase = (t / layer.rotation_period) * 2 * math.pi + layer.phase_offset
            rotation = layer.rotation_amplitude * math.sin(phase)

        painter.save()
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        cx, cy = view_rect.center().x(), view_rect.center().y()

        def _blit(rect: QRectF, pixmap: QPixmap):
            if render_layer.wave_params is not None:
                _draw_waved_pixmap(painter, rect, pixmap, t, render_layer.wave_params)
            else:
                painter.drawPixmap(rect.toRect(), pixmap)

        if layer.motion_mode == "orbit":
            period = max(0.1, layer.orbit_period)
            phase = (t / period) * 2 * math.pi + layer.phase_offset
            ox = layer.orbit_radius * math.cos(phase)
            oy = layer.orbit_radius * math.sin(phase) * 0.6  # slightly flattened, reads as elliptical drift
            painter.translate(cx + ox, cy + oy)
            painter.rotate(rotation)
            painter.scale(scale, scale)
            painter.translate(-tile_w / 2, -tile_h / 2)
            _blit(QRectF(0, 0, tile_w, tile_h), render_layer.pixmap)
        else:
            # Scale/rotation apply to the whole tiled composition as one
            # group — per-tile transforms would introduce their own seams.
            painter.translate(cx, cy)
            painter.rotate(rotation)
            painter.scale(scale, scale)
            painter.translate(-cx, -cy)

            # Python's % always returns a result in [0, tile) for a
            # positive divisor, even when the offset itself is negative
            # (negative speed) — exactly the wrap-around we want.
            offset_x = (view_rect.left() * layer.speed_x) % tile_w
            offset_y = (view_rect.top() * layer.speed_y) % tile_h
            x0 = view_rect.left() - offset_x
            y0 = view_rect.top() - offset_y

            if layer.tile_mode == "fade" and render_layer.faded is not None:
                step = tile_w * 0.85  # slight overlap so the faded edges blend
                for dx in (0.0, step):
                    for dy in (0, tile_h):
                        _blit(QRectF(x0 + dx, y0 + dy, tile_w, tile_h), render_layer.faded)
            else:
                for col, dx in enumerate((0, tile_w)):
                    tile_pixmap = render_layer.pixmap
                    if layer.tile_mode == "mirror" and col % 2 == 1 and render_layer.mirrored is not None:
                        tile_pixmap = render_layer.mirrored
                    for dy in (0, tile_h):
                        _blit(QRectF(x0 + dx, y0 + dy, tile_w, tile_h), tile_pixmap)

        painter.restore()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        if self._parallax_pixmaps:
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            tile_w, tile_h = view_rect.width(), view_rect.height()
            if tile_w > 0 and tile_h > 0:
                t = self._parallax_time()
                for render_layer in self._parallax_pixmaps:
                    self._draw_parallax_layer(painter, view_rect, tile_w, tile_h, render_layer, t)
                painter.setOpacity(1.0)
        elif self._bg_pixmap:
            # Draw the pixmap scaled to fill the visible viewport area
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            painter.drawPixmap(view_rect.toRect(), self._bg_pixmap)
        else:
            super().drawBackground(painter, rect)

    # --- Public API ---

    @property
    def zoom_level(self) -> float:
        return self._zoom

    @property
    def zoom_percent(self) -> int:
        return int(self._zoom * 100)

    @property
    def rotation_deg(self) -> float:
        return self._rotation_deg

    def _rebuild_transform(self):
        """Composes the current zoom and rotation into one transform — used
        by both set_zoom and set_rotation so neither ever wipes out the
        other (a bare `t.scale(...)` replacing the whole transform, like
        this used to do, would silently reset any rotation back to 0)."""
        t = QTransform()
        t.rotate(self._rotation_deg)
        t.scale(self._zoom, self._zoom)
        self.setTransform(t)

    def _reanchor(self, old_scene_pos: QPointF, center: QPointF):
        """Keeps `old_scene_pos` under the same screen `center` point after
        the transform changes — same anchoring trick set_zoom already used
        for the cursor position, reused here for set_rotation too."""
        new_screen_pos = self.mapFromScene(old_scene_pos)
        delta = center - QPointF(new_screen_pos.x(), new_screen_pos.y())
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(delta.x())
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(delta.y())
        )

    def set_zoom(self, level: float, center: QPointF | None = None):
        if level <= 0 or level == self._zoom:
            return

        if center is None:
            center = self.viewport().rect().center()
            center = QPointF(center.x(), center.y())

        old_scene_pos = self.mapToScene(int(center.x()), int(center.y()))
        self._zoom = level
        self._rebuild_transform()
        self._reanchor(old_scene_pos, center)

        self.zoom_changed.emit(self._zoom)
        self.view_changed.emit()

    def set_rotation(self, degrees: float, center: QPointF | None = None):
        degrees = degrees % 360.0
        if degrees == self._rotation_deg:
            return

        if center is None:
            center = self.viewport().rect().center()
            center = QPointF(center.x(), center.y())

        old_scene_pos = self.mapToScene(int(center.x()), int(center.y()))
        self._rotation_deg = degrees
        self._rebuild_transform()
        self._reanchor(old_scene_pos, center)

        self.rotation_changed.emit(self._rotation_deg)
        self.view_changed.emit()

    def zoom_in(self):
        self.set_zoom(self._zoom * Navigation.ZOOM_STEP)

    def zoom_out(self):
        self.set_zoom(self._zoom / Navigation.ZOOM_STEP)

    def zoom_reset(self):
        self.set_zoom(1.0)

    def fit_to_content(self):
        items_rect = self._scene.itemsBoundingRect()
        if items_rect.isEmpty():
            return
        # fitInView builds a fresh axis-aligned transform, discarding any
        # rotation — resync our tracked state to match so a later
        # set_zoom/set_rotation (which reapplies _rotation_deg via
        # _rebuild_transform) doesn't suddenly snap the view back to a
        # rotation that's no longer actually there.
        self.fitInView(items_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = math.hypot(self.transform().m11(), self.transform().m12())
        if self._rotation_deg != 0.0:
            self._rotation_deg = 0.0
            self.rotation_changed.emit(0.0)
        self.zoom_changed.emit(self._zoom)

    def center_on_point(self, scene_pos: QPointF):
        self.centerOn(scene_pos)

    # --- Events ---

    def wheelEvent(self, event: QWheelEvent):
        factor = Navigation.ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / Navigation.ZOOM_STEP
        center = QPointF(event.position().x(), event.position().y())
        self.set_zoom(self._zoom * factor, center)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or self._space_held:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Emit scene coordinates
        scene_pos = self.mapToScene(int(event.position().x()), int(event.position().y()))
        self.cursor_moved.emit(scene_pos.x(), scene_pos.y())

        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            self.view_changed.emit()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (self._panning and not self._space_held):
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().keyReleaseEvent(event)
