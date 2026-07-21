"""Compass — draws the active navigation preset's layer stack (configured in
Config → Navegação) in place of the old hand-painted rosa dos ventos. Each
layer represents one compass part (background, degree ring, needle, core,
glow...) and animates continuously on its own — spinning, pulsing,
blinking, staying fixed, or locked to the map's actual rotation — instead
of a single frame swapping over time. Falls back to the painted needle
whenever no navigation preset is active or has layers, so existing setups
keep working until images are added.

Once attached to a Viewport (attach_viewport):

- Right-button drag, anywhere on the widget, moves the whole compass
  (mirrors MiniMap's plain-drag-to-move — but the left button is already
  busy with rotate/reset below, so moving needed its own button instead of
  a dedicated grip widget/glyph).
- Left-button drag rotates the whole map view (like turning a physical
  board) — but only when the press actually lands on an opaque pixel of
  the active "Anel de rotação" layer (role="ring_degrees"), not just
  anywhere in the annular ring band by distance from center. Hovering that
  same spot (without pressing) draws a soft highlight on the ring so it
  reads as interactive. Falls back to the old distance-based check when no
  such layer is configured (there's no graphic shape to test against).
- A plain left click (or a left-drag on the ring that didn't actually
  move) resets the rotation to north-up; double-clicking expands/collapses
  the compass face, since a single click there is busy being the
  "reset to north" button.

Without an attached viewport the widget behaves exactly as before (no
ring, single left click expands/collapses, no rotation/move drag).

A layer with role="ring_degrees" (Função: "Anel de rotação") is what makes
the ring an actual graphic (with degree markings, etc.) instead of the
plain built-in placeholder (a thin circle + a dot marking north), which
only shows up as a fallback when no such layer is configured. Every
layer — core or ring — scales against the exact same shared baseline
circle (see _layer_baseline_radius); there is no separate per-role size,
only the "Tamanho" (scale) field decides how big each one actually ends
up, so it stays predictable across roles instead of some starting bigger
than others by default.
"""

from dataclasses import dataclass

from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, Signal, QPointF, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QRegion, QPixmap

from src.styles.tokens import Colors
from src.engines.map.navigation import get_navigation_library

import math

# Extra radius (px) added around the core face once a Viewport is attached
# — the band between core edge and this outer edge is the drag-to-rotate
# ring. Zero impact on layout/behavior when no viewport is attached.
_RING_BAND = 36

# Animations that need a continuously-ticking repaint; the rest only need
# to redraw on-demand (locked_to_view redraws via rotation_changed, fixed
# never changes).
_TIMED_ANIMATIONS = {"rotate_cw", "rotate_ccw", "pulse", "blink"}

# Alpha (0-255) above which a pixel counts as "on" the ring graphic for
# hit-testing — low enough to catch anti-aliased edges, high enough to
# ignore near-invisible fringe pixels.
_RING_HIT_ALPHA = 20

# Ring-degree graphics are typically sparse (thin tick marks/text on a
# mostly-transparent ring, not a filled disc) — testing the exact pixel
# under the cursor would make grabbing it frustratingly precise, so a
# small neighborhood around the point counts too.
_RING_HIT_TOLERANCE = 10


@dataclass
class _LayerRender:
    pixmap: QPixmap
    animation: str
    period: float
    opacity: float
    role: str
    scale: float  # fraction of the role's baseline size — see NavigationLayer.scale


def _circle_clip(cx: float, cy: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), r, r)
    return path


def _layer_angle_opacity(layer: "_LayerRender", t: float, viewport) -> tuple[float, float]:
    """Shared animation math for both core layers and the ring_degrees
    layer — same angle/opacity rules regardless of where a layer ends up
    drawn."""
    angle = 0.0
    anim_opacity = 1.0
    if layer.animation == "rotate_cw":
        angle = (t / layer.period) * 360.0
    elif layer.animation == "rotate_ccw":
        angle = -(t / layer.period) * 360.0
    elif layer.animation == "locked_to_view":
        if viewport is not None:
            angle = -viewport.rotation_deg
    elif layer.animation == "pulse":
        phase = (t / layer.period) * 2 * math.pi
        mix = (math.sin(phase) + 1) / 2
        anim_opacity = 0.4 + 0.6 * mix
    elif layer.animation == "blink":
        anim_opacity = 1.0 if (t % layer.period) < layer.period / 2 else 0.0
    # "fixed" (or any unknown value): angle=0, anim_opacity=1 as above.

    # Base opacity (the "Opac." stepper) multiplies with whatever the
    # animation is doing — same convention as ParallaxLayer: lowering it
    # still dims the layer even mid-pulse/blink instead of the animation
    # silently overriding it.
    return angle, layer.opacity * anim_opacity


class Compass(QFrame):
    """Rosa dos ventos / pilha de camadas animadas. Sem Viewport conectado:
    clique único expande/recolhe. Com Viewport conectado: botão direito
    arrasta pra mover; clique/arrasto esquerdo no anel (pixel de verdade da
    camada "Anel de rotação") gira o mapa; clique esquerdo fora do anel
    reseta pro norte; duplo-clique no núcleo expande/recolhe."""

    expanded_changed = Signal(bool)
    moved = Signal()  # emitted once a right-button move-drag ends — mirrors MiniMap.moved

    COLLAPSED_SIZE = 104
    EXPANDED_SIZE = 240

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._layers: list[_LayerRender] = []
        self._ring_layers: list[_LayerRender] = []  # role == "ring_degrees" — drawn in the ring band, not the core
        self._user_positioned = False  # set once dragged with the right button — see has_custom_position()
        self._ring_hover = False  # mouse is over an actual ring-layer pixel (or, with no such layer, the ring band)
        self._widget_hover = False  # mouse is anywhere over the compass — drives animation="interaction" layers' glow

        self._anim_clock = QElapsedTimer()
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self.update)

        self._viewport = None  # attached via attach_viewport(); None => no ring
        self._rotation_drag = False
        self._rotation_drag_moved = False
        self._rotation_drag_start_angle = 0.0
        self._rotation_drag_start_rotation = 0.0

        self._move_drag = False
        self._move_drag_start_global = QPointF()
        self._move_drag_start_pos = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)  # so mouseMoveEvent fires without a button held, for the ring hover highlight
        self._resize_to_state()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        get_navigation_library().changed.connect(self._reload_layers)
        self._reload_layers()

    # ─── Viewport attachment (enables the rotate ring) ──────────────────

    def attach_viewport(self, viewport):
        self._viewport = viewport
        viewport.rotation_changed.connect(lambda _v: self.update())
        self._resize_to_state()
        self.update()

    def _core_size(self) -> int:
        return self.EXPANDED_SIZE if self._expanded else self.COLLAPSED_SIZE

    def _core_radius(self) -> float:
        return self._core_size() / 2

    def _total_size(self) -> int:
        core = self._core_size()
        return core + 2 * _RING_BAND if self._viewport is not None else core

    def _layer_baseline_radius(self) -> float:
        """The one shared "100%" circle every layer scales against,
        regardless of Função — previously each role had its own baseline
        (core for most, core+ring band for outer_glow/ring_degrees), which
        meant "Tamanho" alone couldn't ever grow one layer to meet another
        using a bigger hidden baseline. Now every layer shares this same
        radius — the full outer edge (ring band included, when there is
        one) — so 100% always means the same thing and Tamanho is the only
        knob that matters."""
        return self._core_radius() + (_RING_BAND if self._viewport is not None else 0)

    def _resize_to_state(self):
        size = self._total_size()
        self.setFixedSize(size, size)
        self._apply_style()
        self._apply_mask()

    # ─── Layer stack loading ─────────────────────────────────────────────

    def _reload_layers(self):
        """Re-reads the active navigation preset — called on init and every
        time the library changes, so editing layers in the Config panel
        updates the overlay immediately."""
        preset = get_navigation_library().get_active_preset()
        raw_layers = preset.layers if preset else []

        layers: list[_LayerRender] = []
        ring_layers: list[_LayerRender] = []
        for l in raw_layers:
            pix = QPixmap(l.image_path)
            if pix.isNull():
                continue
            render = _LayerRender(
                pix, l.animation, max(0.1, l.period), max(0.0, min(1.0, l.opacity)), l.role,
                max(0.05, l.scale),
            )
            # "Anel de rotação" is the actual ring graphic — drawn in the ring
            # band around the core (see _paint_ring_layers), not centered on
            # the core like every other role.
            if l.role == "ring_degrees":
                ring_layers.append(render)
            else:
                layers.append(render)

        self._layers = layers
        self._ring_layers = ring_layers

        self._apply_style()
        self._apply_mask()

        # Only ticks while at least one layer actually needs continuous
        # redraws — a stack of only "fixed"/"locked_to_view" layers never
        # needs this (locked_to_view repaints via rotation_changed instead).
        if any(l.animation in _TIMED_ANIMATIONS for l in layers + ring_layers):
            if not self._anim_clock.isValid():
                self._anim_clock.start()
            self._anim_timer.start(33)  # ~30fps
        else:
            self._anim_timer.stop()
        self.update()

    def _anim_time(self) -> float:
        return self._anim_clock.elapsed() / 1000.0 if self._anim_clock.isValid() else 0.0

    def _apply_mask(self):
        """Máscara circular — cobre o núcleo sozinho, ou núcleo+anel quando
        há um Viewport conectado (senão o anel ficaria fora da área
        clicável do widget)."""
        size = self.width()
        region = QRegion(0, 0, size, size, QRegion.RegionType.Ellipse)
        self.setMask(region)

    def _apply_style(self):
        # With a ring attached, or with image layers, the widget paints its
        # own circle(s) by hand in paintEvent — a QSS background sized to
        # the core would mismatch the (now larger) total widget rect.
        if self._layers or self._ring_layers or self._viewport is not None:
            self.setStyleSheet("QFrame { background: transparent; border: none; }")
            return
        radius = self._core_size() // 2
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: {radius}px;
            }}
        """)

    def is_expanded(self) -> bool:
        return self._expanded

    def has_custom_position(self) -> bool:
        """Whether the user has dragged this compass (right-button drag) —
        mirrors MiniMap.has_custom_position(), so main_layout.py's
        resizeEvent can clamp a user-chosen spot instead of overriding it
        with the default top-right anchor."""
        return self._user_positioned

    def _toggle_expanded(self):
        self._expanded = not self._expanded
        self._resize_to_state()
        self.expanded_changed.emit(self._expanded)
        self.update()

    # ─── Mouse: right-drag anywhere moves; left-drag on the ring's actual
    # pixels rotates; left click elsewhere resets/expands ────────────────

    def _ring_layer_hit(self, pos: QPointF) -> bool:
        """Whether `pos` (widget coords) lands on an actual opaque pixel of
        a ring_degrees layer, accounting for its current rotation — so
        rotate-drag only grabs where the ring graphic visually is, not
        just anywhere in the annular band by distance. Falls back to the
        plain distance check when no such layer is configured (the
        built-in placeholder ring has no real shape to test against)."""
        cx, cy = self.width() / 2, self.height() / 2

        if not self._ring_layers:
            return math.hypot(pos.x() - cx, pos.y() - cy) > self._core_radius()

        base_r = self._layer_baseline_radius()
        t = self._anim_time()
        dx, dy = pos.x() - cx, pos.y() - cy

        for layer in self._ring_layers:
            angle, opacity = _layer_angle_opacity(layer, t, self._viewport)
            if opacity <= 0.0:
                continue
            # Match what's actually rendered (_draw_layer_pixmap scales
            # against the same shared baseline, times layer.scale).
            layer_size = max(1, int(base_r * 2 * layer.scale))
            scaled = layer.pixmap.scaled(
                layer_size, layer_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )
            # Undo translate+rotate to map the point into this layer's own
            # (unrotated, pixmap-local) coordinate space.
            rad = math.radians(-angle)
            lx = dx * math.cos(rad) - dy * math.sin(rad) + scaled.width() / 2
            ly = dx * math.sin(rad) + dy * math.cos(rad) + scaled.height() / 2
            px, py = int(lx), int(ly)

            img = scaled.toImage()
            w, h = img.width(), img.height()
            # Small neighborhood, not just the exact pixel — see
            # _RING_HIT_TOLERANCE.
            step = max(1, _RING_HIT_TOLERANCE // 3)
            for oy in range(-_RING_HIT_TOLERANCE, _RING_HIT_TOLERANCE + 1, step):
                sy = py + oy
                if not (0 <= sy < h):
                    continue
                for ox in range(-_RING_HIT_TOLERANCE, _RING_HIT_TOLERANCE + 1, step):
                    sx = px + ox
                    if 0 <= sx < w and img.pixelColor(sx, sy).alpha() > _RING_HIT_ALPHA:
                        return True
        return False

    def mousePressEvent(self, event):
        pos = event.position()

        if event.button() == Qt.MouseButton.RightButton and self._viewport is not None:
            self._move_drag = True
            self._move_drag_start_global = event.globalPosition().toPoint()
            self._move_drag_start_pos = self.pos()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._viewport is not None and self._ring_layer_hit(pos):
            cx, cy = self.width() / 2, self.height() / 2
            self._rotation_drag = True
            self._rotation_drag_moved = False
            self._rotation_drag_start_angle = math.degrees(math.atan2(pos.y() - cy, pos.x() - cx))
            self._rotation_drag_start_rotation = self._viewport.rotation_deg
            return

        if self._viewport is not None:
            # Click's job outside the ring is "back to north" — expand/
            # collapse moved to double-click (see mouseDoubleClickEvent) so
            # it doesn't fight this on every single click.
            self._viewport.set_rotation(0.0)
        else:
            # No viewport attached (ring disabled) — behave exactly like
            # before the ring existed.
            self._toggle_expanded()

    def mouseMoveEvent(self, event):
        pos = event.position()

        if self._move_drag:
            delta = event.globalPosition().toPoint() - self._move_drag_start_global
            self.move(self._move_drag_start_pos + delta)
            self._user_positioned = True
            return

        if self._rotation_drag and self._viewport is not None:
            cx, cy = self.width() / 2, self.height() / 2
            angle = math.degrees(math.atan2(pos.y() - cy, pos.x() - cx))
            delta = angle - self._rotation_drag_start_angle
            if abs(delta) > 1.0:
                self._rotation_drag_moved = True
            self._viewport.set_rotation(self._rotation_drag_start_rotation + delta)
            return

        # Not dragging anything — just track hover for the ring highlight.
        if self._viewport is not None:
            hovering = self._ring_layer_hit(pos)
            if hovering != self._ring_hover:
                self._ring_hover = hovering
                self.update()

    def mouseReleaseEvent(self, event):
        if self._move_drag:
            self._move_drag = False
            self.moved.emit()
            return

        # A press-release on the ring with no real movement is just a
        # click, not a drag — treat it the same as clicking outside the
        # ring: reset to north, instead of silently doing nothing.
        if self._rotation_drag and not self._rotation_drag_moved and self._viewport is not None:
            self._viewport.set_rotation(0.0)
        self._rotation_drag = False

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._viewport is None:
            return
        if self._ring_layer_hit(event.position()):
            self._viewport.set_rotation(0.0)
        else:
            self._toggle_expanded()

    def enterEvent(self, event):
        self._widget_hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._widget_hover = False
        self._ring_hover = False
        self.update()
        super().leaveEvent(event)

    # ─── Paint ────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        core_r = self._core_radius()

        if self._viewport is not None:
            # QSS background is disabled while a ring exists (see
            # _apply_style) — paint the core's own circle by hand first, so
            # the ring band around it reads as a distinct, separate track.
            if not self._layers:
                p.setPen(QPen(QColor(Colors.GLASS_BORDER), 1))
                p.setBrush(QColor(Colors.GLASS_BG_STRONG))
                p.drawEllipse(QPointF(cx, cy), core_r, core_r)
            if self._ring_layers:
                self._paint_ring_layers(p, cx, cy, core_r)
            else:
                # No "Anel de rotação" layer configured — simple built-in
                # placeholder ring (thin track + a dot marking north).
                self._paint_ring(p, cx, cy, core_r)
            if self._ring_hover:
                self._paint_ring_highlight(p, cx, cy, core_r)

        self._paint_layers(p, cx, cy, core_r)

        p.end()

    def _paint_ring_highlight(self, p: QPainter, cx: float, cy: float, core_r: float):
        """Soft glow traced over the ring band when the mouse is hovering
        an actual ring-graphic pixel — the "efeito de destaque" that shows
        the ring is the thing you'd drag to rotate, like highlighting one
        layer of an onion."""
        p.save()
        p.setPen(QPen(QColor(Colors.ACCENT), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setOpacity(0.55)
        mid_r = core_r + _RING_BAND / 2
        p.drawEllipse(QPointF(cx, cy), mid_r, mid_r)
        p.restore()

    def _paint_ring(self, p: QPainter, cx: float, cy: float, core_r: float):
        outer_r = core_r + _RING_BAND - 5
        p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # North marker — starts pointing up (-90°) and turns opposite the
        # map's rotation, so it always shows where geographic north
        # currently points on the rotated view.
        marker_angle = math.radians(-90 - self._viewport.rotation_deg)
        mx = cx + outer_r * math.cos(marker_angle)
        my = cy + outer_r * math.sin(marker_angle)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Colors.ACCENT))
        p.drawEllipse(QPointF(mx, my), 7, 7)

    def _paint_ring_layers(self, p: QPainter, cx: float, cy: float, core_r: float):
        """The 'Anel de rotação' layer(s) — same shared baseline as every
        other layer (see _layer_baseline_radius); "Tamanho" is what
        actually decides how far out this one reaches."""
        base_r = self._layer_baseline_radius()
        t = self._anim_time()
        for layer in self._ring_layers:
            angle, opacity = _layer_angle_opacity(layer, t, self._viewport)
            if opacity <= 0.0:
                continue
            self._draw_layer_pixmap(p, layer, cx, cy, base_r, angle, opacity)

    def _paint_layers(self, p: QPainter, cx: float, cy: float, core_r: float):
        if not self._layers:
            self._paint_fallback(p, cx, cy, core_r)
            return

        base_r = self._layer_baseline_radius()
        t = self._anim_time()
        for layer in self._layers:
            angle, opacity = _layer_angle_opacity(layer, t, self._viewport)
            if opacity <= 0.0:
                continue
            self._draw_layer_pixmap(p, layer, cx, cy, base_r, angle, opacity)

    def _draw_layer_pixmap(self, p: QPainter, layer: _LayerRender, cx: float, cy: float,
                            base_r: float, angle: float, opacity: float):
        """`base_r` is the one shared baseline every layer scales against
        (see _layer_baseline_radius) — every layer gets the same starting
        point, so `layer.scale` (the "Tamanho" stepper) alone controls how
        far each one actually reaches, with no hidden per-role multiplier
        fighting it. 120% genuinely reaches further out than 100%, all the
        way past the ring band if pushed high enough (the widget's own
        circular mask is still the hard ceiling). Scales to COVER the
        resulting box (cropping overflow) rather than fit inside it, so a
        layer with a different aspect ratio than the others (e.g. a wide
        1536x1024 border asset next to square 1024x1024 ones) still fully
        fills its circle instead of shrinking to letterbox."""
        effective_r = base_r * layer.scale
        target_size = max(1, int(effective_r * 2))
        scaled = layer.pixmap.scaled(
            target_size, target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        p.save()
        p.setClipPath(_circle_clip(cx, cy, effective_r))
        p.setOpacity(opacity)
        p.translate(cx, cy)
        if angle:
            p.rotate(angle)
        p.drawPixmap(QPointF(-scaled.width() / 2, -scaled.height() / 2), scaled)
        p.restore()

        if layer.animation == "interaction" and self._widget_hover:
            self._paint_interaction_glow(p, scaled, cx, cy, angle, effective_r)

    def _paint_interaction_glow(self, p: QPainter, scaled: QPixmap, cx: float, cy: float,
                                 angle: float, effective_r: float):
        """The "Interação" animation's payoff — a layer with this animation
        renders exactly like "Fixo na tela" (see _layer_angle_opacity's
        fallthrough) until the mouse is anywhere over the compass, at which
        point it brightens. No separate colored shape drawn behind/around
        it — just the layer's own pixmap stamped again on top of itself
        with additive blending, so only the artwork's own colors intensify
        (a blue needle gets brighter blue, not a foreign accent-colored
        halo bleeding past its edges)."""
        p.save()
        p.setClipPath(_circle_clip(cx, cy, effective_r))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setOpacity(0.55)
        p.translate(cx, cy)
        if angle:
            p.rotate(angle)
        p.drawPixmap(QPointF(-scaled.width() / 2, -scaled.height() / 2), scaled)
        p.restore()

    def _paint_fallback(self, p: QPainter, cx: float, cy: float, core_r: float):
        radius = core_r - 8

        if self._expanded:
            # Círculo externo
            p.setPen(QPen(QColor(Colors.BORDER_SUBTLE), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

            # Direções cardinais
            directions = [("N", -90), ("E", 0), ("S", 90), ("W", 180)]
            sub_dirs = [("NE", -45), ("SE", 45), ("SW", 135), ("NW", -135)]

            p.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
            for label, angle in directions:
                rad = math.radians(angle)
                x = cx + (radius - 20) * math.cos(rad)
                y = cy + (radius - 20) * math.sin(rad)
                color = Colors.ACCENT if label == "N" else Colors.TEXT_MUTED
                p.setPen(QColor(color))
                p.drawText(QPointF(x - 9, y + 7), label)

            p.setFont(QFont("Segoe UI", 13))
            p.setPen(QColor(Colors.TEXT_MUTED))
            for label, angle in sub_dirs:
                rad = math.radians(angle)
                x = cx + (radius - 24) * math.cos(rad)
                y = cy + (radius - 24) * math.sin(rad)
                p.drawText(QPointF(x - 9, y + 6), label)

            # Agulha
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Colors.ACCENT))
            needle_len = radius * 0.5
            p.drawPolygon([
                QPointF(cx, cy - needle_len),
                QPointF(cx - 7, cy),
                QPointF(cx + 7, cy),
            ])
            p.setBrush(QColor(Colors.TEXT_MUTED))
            p.drawPolygon([
                QPointF(cx, cy + needle_len * 0.6),
                QPointF(cx - 5, cy),
                QPointF(cx + 5, cy),
            ])
        else:
            # Modo compacto — só "N"
            p.setPen(QColor(Colors.ACCENT))
            p.setFont(QFont("Segoe UI", 32, QFont.Weight.Black))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "N")
