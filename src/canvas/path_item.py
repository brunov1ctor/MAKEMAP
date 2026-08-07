"""PathItem — animated river and road items with editable bezier points.

RiverPathItem: tiled water texture + flow animation (moving highlight streaks
               + foam particles drifting downstream).
RoadPathItem:  tiled road texture + life animation (dust puffs drifting off
               the edges + subtle shimmer along the surface).

Both share the same point/handle editing model:
  - Left-click on empty path area  → add point
  - Left-drag on a point handle    → move point
  - Left-drag on a bezier handle   → adjust curve
  - Right-click on a point handle  → remove point
  - Double-click anywhere          → finalize (lock editing)
  - ESC                            → cancel / delete
"""

from __future__ import annotations

import math
import random
import time
import weakref
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QPixmap,
    QRadialGradient, QImage,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from src.canvas.item_utils import suppress_selection_decoration

if TYPE_CHECKING:
    pass


# ─── Shared helpers ──────────────────────────────────────────────────────────

def _build_edge_mask(size: QSize, clip_path: QPainterPath, origin: QPointF, feather_px: float) -> QImage:
    """Solid fill of `clip_path` (translated so `origin` lands at (0, 0),
    matching the tile buffer's own coordinate space), then blurred at the
    edges with the same cheap downscale/smooth-upscale idiom as
    viewport.py's _apply_blur() — used to fade a river/road's texture out
    gradually at its boundary instead of the hard clip-path cut this used
    to be."""
    mask = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    mask.fill(QColor(0, 0, 0, 0))
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing)
    mp.translate(-origin.x(), -origin.y())
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(255, 255, 255, 255))
    mp.drawPath(clip_path)
    mp.end()

    factor = max(1, int(feather_px))
    if factor < 2 or size.width() <= 0 or size.height() <= 0:
        return mask
    w, h = size.width(), size.height()
    small = QPixmap.fromImage(mask).scaled(
        max(1, w // factor), max(1, h // factor),
        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    blurred = small.scaled(
        w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    return blurred.toImage()


def _draw_texture_along_path(
    painter: QPainter,
    path: QPainterPath,
    texture: QPixmap,
    width: float,
    tex_offset: float = 0.0,
    clip_path: QPainterPath | None = None,
    owner: "_BasePathItem | None" = None,
    feather_px: float = 0.0,
):
    """Stamp the texture along the path, rotated to follow the tangent,
    overlapping by 50% so there are no gaps. tex_offset scrolls the tile
    sequence along the path for the flow animation.

    Scales each tile UNIFORMLY (fit the texture's own height to `width`),
    instead of independently squashing width/height to force every stamp
    into a square width×width footprint — that old per-axis scale ignored
    the texture's real aspect ratio, so any non-square tile (a wide ocean
    or road texture — the common case for these assets) came out visibly
    stretched/squashed. A uniform scale keeps the tile looking like the
    source art; the along-path tile length is however long that scaled
    tile naturally comes out to, not forced to equal `width`.

    Tiles are composited onto an intermediate buffer using CompositionMode_Source
    so overlapping semi-transparent tile edges don't accumulate alpha and create
    visible transparent bands where tiles meet.

    `clip_path` + `feather_px > 0` fades the texture's alpha out gradually at
    the boundary (see _build_edge_mask) instead of a hard cut; `owner`, when
    given, caches that mask on the item so it's rebuilt only when the path's
    geometry actually changes (see _rebuild()), not on every animation-driven
    repaint. `feather_px == 0` (the default) falls back to the old hard
    clipPath cut, for callers that don't want feathering."""
    if texture.isNull() or path.isEmpty():
        return
    total_len = path.length()
    if total_len < 1:
        return
    tw = texture.width()
    th = texture.height()
    if tw == 0 or th == 0:
        return
    scale = width / th
    stamp_len = tw * scale         # on-screen path-length one full tile covers
    step = max(1.0, stamp_len * 0.5)  # 50% overlap → no gaps

    # Render all tiles onto an intermediate buffer using CompositionMode_Source
    # so overlapping tiles replace rather than blend — prevents semi-transparent
    # tile edges from accumulating alpha and creating visible transparent bands.
    bounds = path.boundingRect().adjusted(-stamp_len, -width, stamp_len, width)
    buf = QImage(bounds.size().toSize(), QImage.Format.Format_ARGB32_Premultiplied)
    buf.fill(QColor(0, 0, 0, 0))
    bp = QPainter(buf)
    bp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    bp.translate(-bounds.topLeft())
    bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)

    def _stamp_at(t: float):
        pt = path.pointAtPercent(t)
        angle = path.angleAtPercent(t)  # degrees, CCW from +X
        bp.save()
        bp.translate(pt.x(), pt.y())
        bp.rotate(-angle)           # align tile to tangent
        bp.translate(-stamp_len / 2, -width / 2)
        bp.scale(scale, scale)
        bp.drawPixmap(0, 0, texture)
        bp.restore()

    # Scroll the tile SEQUENCE along the path (not which texture pixels get
    # sampled) — visually equivalent for a seamlessly-tileable texture,
    # without reintroducing a stretch-causing per-stamp crop width.
    dist = -((tex_offset * scale) % step)
    last_dist = None
    while dist <= total_len:
        if dist >= 0:
            _stamp_at(min(dist / total_len, 1.0))
            last_dist = dist
        dist += step

    # The spaced-out loop above always lands a stamp exactly on t=0 (dist
    # starts at 0, or below), but the LAST stamp before dist overshoots
    # total_len can fall up to `step` short of the true endpoint — so the
    # path's tail got whatever mid-tile texture happened to land there
    # instead of a tile actually centered on the tip, unlike the start.
    # The round-cap clip is symmetric either way, but the tile CONTENT
    # under it wasn't — this is what made the end look flatter/less
    # rounded than the start. Force one more stamp dead-center on the
    # endpoint to match.
    if last_dist is None or last_dist < total_len - 0.5:
        _stamp_at(1.0)

    bp.end()

    if clip_path is not None and feather_px > 0:
        # Soft edge: multiply the tile buffer's alpha by a blurred fill of
        # clip_path instead of hard-clipping the blit below — cached on
        # `owner` since the mask only depends on path geometry, not the
        # per-frame flow animation (_rebuild() clears the cache whenever
        # that geometry actually changes).
        size = bounds.size().toSize()
        mask = owner._edge_mask if owner is not None else None
        if mask is None or mask.size() != size:
            mask = _build_edge_mask(size, clip_path, bounds.topLeft(), feather_px)
            if owner is not None:
                owner._edge_mask = mask
        mp = QPainter(buf)
        mp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        mp.drawImage(0, 0, mask)
        mp.end()

    # Blit the buffer onto the scene painter — already soft-edged above if
    # feathering was requested, otherwise fall back to a hard clip.
    painter.save()
    if clip_path is not None and feather_px <= 0:
        painter.setClipPath(clip_path)
    painter.drawImage(bounds.topLeft(), buf)
    painter.restore()


def _path_from_points(points: list[QPointF],
                      controls_out: list[QPointF | None],
                      controls_in: list[QPointF | None]) -> QPainterPath:
    """Build a QPainterPath from point list + optional bezier handles."""
    path = QPainterPath()
    if len(points) < 2:
        if points:
            path.moveTo(points[0])
        return path
    path.moveTo(points[0])
    for i in range(1, len(points)):
        co = controls_out[i - 1]
        ci = controls_in[i]
        if co and ci:
            path.cubicTo(co, ci, points[i])
        elif co:
            path.quadTo(co, points[i])
        elif ci:
            path.quadTo(ci, points[i])
        else:
            path.lineTo(points[i])
    return path


def _auto_controls(points: list[QPointF],
                   tension: float = 0.35) -> tuple[list[QPointF | None], list[QPointF | None]]:
    """Catmull-Rom → bezier: auto-compute smooth handles from point list."""
    n = len(points)
    cout: list[QPointF | None] = [None] * n
    cin: list[QPointF | None] = [None] * n
    for i in range(n):
        p0 = points[max(0, i - 1)]
        p1 = points[i]
        p2 = points[min(n - 1, i + 1)]
        p3 = points[min(n - 1, i + 2)]
        if i < n - 1:
            cout[i] = QPointF(
                p1.x() + (p2.x() - p0.x()) * tension,
                p1.y() + (p2.y() - p0.y()) * tension,
            )
        if i > 0:
            cin[i] = QPointF(
                p1.x() - (p2.x() - p0.x()) * tension,  # mirror of cout's tangent
                p1.y() - (p2.y() - p0.y()) * tension,
            )
    # Endpoints: no handle pointing outward
    cout[n - 1] = None
    cin[0] = None
    return cout, cin


# ─── Particle ────────────────────────────────────────────────────────────────

class _Particle:
    __slots__ = ("t", "offset", "alpha", "size", "speed", "life", "max_life", "_peak_alpha", "_fade_in", "_fade_out")

    def __init__(self, t: float, offset: float, alpha: float, size: float, speed: float):
        self.t = t          # 0-1 along path
        self.offset = offset  # lateral offset in px
        self.alpha = alpha
        self.size = size
        self.speed = speed  # t-units per second
        self.life = random.uniform(0.0, 1.0)   # current life phase 0-1
        self.max_life = random.uniform(0.4, 1.2)  # seconds for full cycle


# ─── Base animated path item ─────────────────────────────────────────────────

class _BasePathItem(QGraphicsItem):
    """Shared base: point storage, handle drawing, hit-test, animation tick."""

    HANDLE_R = 6.0
    BEZIER_HANDLE_R = 4.0
    ANIM_INTERVAL_MS = 50   # ~20 fps animation

    # One shared timer drives every path item's animation tick instead of
    # each river/road owning its own QTimer — a map with many paths used to
    # accumulate one independent 20fps Python callback per item, which adds
    # up fast. Stops itself when the last path item is gone, restarts on
    # the next one created.
    _shared_timer: QTimer | None = None
    _live_instances: "weakref.WeakSet[_BasePathItem]" = weakref.WeakSet()

    @classmethod
    def _tick_all(cls):
        for item in list(cls._live_instances):
            try:
                item._tick()
            except RuntimeError:
                # Underlying C++ object already deleted (item removed from
                # the scene and collected) — drop it instead of retrying
                # every tick forever.
                cls._live_instances.discard(item)
        if not cls._live_instances and cls._shared_timer is not None:
            cls._shared_timer.stop()

    def __init__(self, width: float, texture: QPixmap | None, parent=None):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        suppress_selection_decoration(self)

        self._width = width
        self._texture = texture

        # Point data
        self._points: list[QPointF] = []
        self._controls_out: list[QPointF | None] = []
        self._controls_in: list[QPointF | None] = []

        # Editing state
        self._editing = True          # False once finalized
        self._dragging_idx: int = -1  # point index being dragged
        self._dragging_handle: tuple[int, str] | None = None  # (idx, "in"|"out")
        self._hovered_idx: int = -1
        self._lock_drag = False       # True while tool is pulling handles externally

        # Cached path
        self._path: QPainterPath = QPainterPath()
        self._bounds: QRectF = QRectF()

        # Cached soft-edge mask (see _draw_texture_along_path /
        # _build_edge_mask) — depends only on path geometry, so it's
        # invalidated in _rebuild() rather than rebuilt on every repaint.
        self._edge_mask: QImage | None = None

        # Animation — see _shared_timer above
        self._particles: list[_Particle] = []
        _BasePathItem._live_instances.add(self)
        if _BasePathItem._shared_timer is None:
            _BasePathItem._shared_timer = QTimer()
            _BasePathItem._shared_timer.setInterval(_BasePathItem.ANIM_INTERVAL_MS)
            _BasePathItem._shared_timer.timeout.connect(_BasePathItem._tick_all)
        if not _BasePathItem._shared_timer.isActive():
            _BasePathItem._shared_timer.start()
        self._t0 = time.monotonic()

    # ─── Public API ──────────────────────────────────────────────────────

    def add_point(self, pos: QPointF):
        self._points.append(pos)
        self._controls_out.append(None)
        self._controls_in.append(None)
        self._rebuild()

    def drag_last_point_handles(self, drag_pos: QPointF):
        """Called while dragging after placing the last point.
        Sets symmetric bezier handles: out toward drag, in mirrored."""
        if not self._points:
            return
        idx = len(self._points) - 1
        anchor = self._points[idx]
        dx = drag_pos.x() - anchor.x()
        dy = drag_pos.y() - anchor.y()
        self._controls_out[idx] = QPointF(anchor.x() + dx, anchor.y() + dy)
        self._controls_in[idx] = QPointF(anchor.x() - dx, anchor.y() - dy)
        self._lock_drag = True
        self._rebuild()

    def release_drag_lock(self):
        self._lock_drag = False

    def finalize(self):
        self._editing = False
        self._dragging_idx = -1
        self._dragging_handle = None
        self._hovered_idx = -1
        self.update()

    def is_editing(self) -> bool:
        return self._editing

    def point_count(self) -> int:
        return len(self._points)

    def load_points(self, points: list[QPointF], controls_out: list[QPointF | None],
                     controls_in: list[QPointF | None]):
        """Bulk-restore point/handle data from persistence (see
        BrushMediator._load_from_db) — bypasses the interactive add_point/
        drag flow used while tracing a new path, then finalizes directly
        since a reloaded path is never re-entered into edit mode."""
        self._points = list(points)
        self._controls_out = list(controls_out)
        self._controls_in = list(controls_in)
        self._rebuild()
        self.finalize()

    def export_points(self) -> tuple[list[QPointF], list[QPointF | None], list[QPointF | None]]:
        """Inverse of load_points — read back by BrushMediator._sync_to_db
        to persist the current geometry."""
        return list(self._points), list(self._controls_out), list(self._controls_in)

    @property
    def width(self) -> float:
        return self._width

    def set_width(self, w: float):
        self._width = max(2.0, w)
        self.prepareGeometryChange()
        self._rebuild()

    def set_texture(self, pixmap: QPixmap | None):
        self._texture = pixmap
        self.update()

    # ─── Geometry ────────────────────────────────────────────────────────

    def _rebuild(self):
        self._edge_mask = None
        if len(self._points) < 2:
            self._path = QPainterPath()
            if self._points:
                self._path.moveTo(self._points[0])
            self._bounds = QRectF()
            self.prepareGeometryChange()
            self.update()
            return
        # Auto-smooth handles for points without explicit handles
        auto_out, auto_in = _auto_controls(self._points)
        cout = [self._controls_out[i] or auto_out[i] for i in range(len(self._points))]
        cin = [self._controls_in[i] or auto_in[i] for i in range(len(self._points))]
        self._path = _path_from_points(self._points, cout, cin)
        pad = self._width / 2 + self.HANDLE_R + 4
        self._bounds = self._path.boundingRect().adjusted(-pad, -pad, pad, pad)
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        if self._bounds.isEmpty() and self._points:
            r = self.HANDLE_R + 4
            return QRectF(self._points[0].x() - r, self._points[0].y() - r, r * 2, r * 2)
        return self._bounds

    def shape(self) -> QPainterPath:
        if self._path.isEmpty():
            return QPainterPath()
        stroker_path = QPainterPath()
        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(self._width + 8)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroker_path = stroker.createStroke(self._path)
        # A tight bend makes the stroked outline self-overlap (the two
        # offset sides cross); the default OddEvenFill treats that
        # double-covered sliver as OUTSIDE the shape, making the item
        # unclickable right at the bend. WindingFill keeps any
        # positively-covered area solid regardless of overlap — same fix as
        # map_boundary.py's clover boundary.
        stroker_path.setFillRule(Qt.FillRule.WindingFill)
        return stroker_path

    # ─── Hit-test helpers ────────────────────────────────────────────────

    def _point_at(self, pos: QPointF) -> int:
        for i, p in enumerate(self._points):
            if (p - pos).manhattanLength() < self.HANDLE_R * 2:
                return i
        return -1

    def _handle_at(self, pos: QPointF) -> tuple[int, str] | None:
        for i in range(len(self._points)):
            for key, ctrl in (("out", self._controls_out[i]), ("in", self._controls_in[i])):
                if ctrl and (ctrl - pos).manhattanLength() < self.BEZIER_HANDLE_R * 2.5:
                    return (i, key)
        return None

    # ─── Mouse events ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self._editing or self._lock_drag:
            super().mousePressEvent(event)
            return
        pos = event.pos()
        if event.button() == Qt.MouseButton.RightButton:
            idx = self._point_at(pos)
            if idx >= 0 and len(self._points) > 2:
                self._points.pop(idx)
                self._controls_out.pop(idx)
                self._controls_in.pop(idx)
                self._rebuild()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._handle_at(pos)
            if handle:
                self._dragging_handle = handle
                event.accept()
                return
            idx = self._point_at(pos)
            if idx >= 0:
                self._dragging_idx = idx
                event.accept()
                return
        super().mousePressEvent(event)

    def move_handle(self, idx: int, key: str, pos: QPointF):
        """Move bezier handle `idx`/`key` ("in"|"out") to `pos` (item-local
        coords) and mirror it onto the adjacent point's opposite handle for
        a smooth curve. Called directly by _BasePathTool.mouse_move — see
        mouseMoveEvent's docstring note on why Qt never delivers this event
        itself in this app."""
        if key == "out":
            self._controls_out[idx] = pos
            # Mirror to in-handle of next point for smooth curve
            if idx + 1 < len(self._points):
                anchor = self._points[idx]
                dx = pos.x() - anchor.x()
                dy = pos.y() - anchor.y()
                self._controls_in[idx + 1] = QPointF(anchor.x() - dx, anchor.y() - dy)
        else:
            self._controls_in[idx] = pos
            if idx - 1 >= 0:
                anchor = self._points[idx]
                dx = pos.x() - anchor.x()
                dy = pos.y() - anchor.y()
                self._controls_out[idx - 1] = QPointF(anchor.x() - dx, anchor.y() - dy)
        self._rebuild()

    def move_point(self, idx: int, pos: QPointF):
        """Move anchor point `idx` to `pos` (item-local coords), carrying
        its own handles and any neighbor's explicit handle pointing at it
        along by the same delta. Called directly by _BasePathTool.
        mouse_move — see mouseMoveEvent's docstring note."""
        delta = pos - self._points[idx]
        self._points[idx] = pos
        # Move associated handles with the point
        if self._controls_out[idx]:
            co = self._controls_out[idx]
            self._controls_out[idx] = QPointF(co.x() + delta.x(), co.y() + delta.y())
        if self._controls_in[idx]:
            ci = self._controls_in[idx]
            self._controls_in[idx] = QPointF(ci.x() + delta.x(), ci.y() + delta.y())
        # Also move neighbors' explicit handles that point at this
        # anchor (e.g. mirrored from a manual handle drag) — otherwise
        # they stay frozen at the old position and the curve kinks/
        # breaks at this point once it moves.
        if idx - 1 >= 0 and self._controls_out[idx - 1]:
            co = self._controls_out[idx - 1]
            self._controls_out[idx - 1] = QPointF(co.x() + delta.x(), co.y() + delta.y())
        if idx + 1 < len(self._points) and self._controls_in[idx + 1]:
            ci = self._controls_in[idx + 1]
            self._controls_in[idx + 1] = QPointF(ci.x() + delta.x(), ci.y() + delta.y())
        self._rebuild()

    def mouseMoveEvent(self, event):
        # NOTE: CanvasEngine fully monkeypatches the viewport's mouse events
        # to route through the active Tool instead of Qt's normal
        # QGraphicsView -> QGraphicsScene -> item dispatch (see
        # CanvasEngine._on_mouse_press's docstring comment), so this handler
        # never actually fires in the running app — _BasePathTool.mouse_move
        # calls move_point/move_handle above directly instead. Kept here
        # (dead in practice) only in case something ever re-enables real Qt
        # event delivery to scene items.
        if not self._editing or self._lock_drag:
            super().mouseMoveEvent(event)
            return
        pos = event.pos()
        if self._dragging_handle:
            idx, key = self._dragging_handle
            self.move_handle(idx, key, pos)
            event.accept()
            return
        if self._dragging_idx >= 0:
            self.move_point(self._dragging_idx, pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging_idx = -1
        self._dragging_handle = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._editing and len(self._points) >= 2:
            self.finalize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def hoverMoveEvent(self, event):
        if self._editing:
            self._hovered_idx = self._point_at(event.pos())
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered_idx = -1
        self.update()
        super().hoverLeaveEvent(event)

    # ─── Animation ───────────────────────────────────────────────────────

    def _tick(self):
        self._update_particles()
        self.update()

    def _update_particles(self):
        raise NotImplementedError

    # ─── Handle drawing (shared) ─────────────────────────────────────────

    def _draw_handles(self, painter: QPainter):
        if not self._editing:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Bezier control handles
        for i in range(len(self._points)):
            for ctrl in (self._controls_out[i], self._controls_in[i]):
                if ctrl:
                    painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(self._points[i], ctrl)
                    painter.setPen(QPen(QColor(200, 200, 255, 200), 1))
                    painter.setBrush(QBrush(QColor(100, 100, 200, 180)))
                    painter.drawEllipse(ctrl, self.BEZIER_HANDLE_R, self.BEZIER_HANDLE_R)

        # Point handles
        for i, p in enumerate(self._points):
            hovered = (i == self._hovered_idx)
            color = QColor(255, 220, 50) if hovered else QColor(255, 255, 255)
            painter.setPen(QPen(QColor(0, 0, 0, 180), 1.5))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(p, self.HANDLE_R, self.HANDLE_R)

        painter.restore()


# ─── River Path Item ─────────────────────────────────────────────────────────

class RiverPathItem(_BasePathItem):
    """Animated river: tiled water texture that fades at the edges to blend
    naturally into the terrain. Minimal flow animation (barely perceptible
    shimmer streaks). Center dashed line only when selected."""

    def __init__(self, width: float = 30.0, texture: QPixmap | None = None,
                 flow_direction: float = 1.0, parent=None):
        super().__init__(width, texture, parent)
        self._flow_dir = flow_direction
        self._tex_offset = 0.0
        self._scroll_speed = random.uniform(4.0, 9.0)
        self._scroll_osc_period = random.uniform(10.0, 20.0)
        self._scroll_osc_phase = random.uniform(0.0, math.tau)
        self._scroll_osc_amp = random.uniform(0.15, 0.35)
        self.setZValue(7)
        self._spawn_particles()

    def _spawn_particles(self):
        self._particles = []
        for _ in range(random.randint(5, 12)):
            p = _Particle(
                t=random.random(),
                offset=random.uniform(-0.4, 0.4),
                alpha=0.0,
                size=random.uniform(3.0, 9.0),
                speed=random.uniform(0.01, 0.04) * random.choice([-1, 1]) * self._flow_dir,
            )
            p.max_life = random.uniform(0.6, 2.0)
            p.life = random.uniform(0.0, p.max_life)
            p._peak_alpha = random.uniform(0.04, 0.14)
            p._fade_in = random.uniform(0.2, 0.4)
            p._fade_out = random.uniform(0.2, 0.4)
            self._particles.append(p)

    def _update_particles(self):
        dt = self.ANIM_INTERVAL_MS / 1000.0
        elapsed = time.monotonic() - self._t0
        osc = 1.0 + self._scroll_osc_amp * math.sin(
            2 * math.pi * elapsed / self._scroll_osc_period + self._scroll_osc_phase)
        self._tex_offset = (self._tex_offset + dt * self._scroll_speed * osc) % 512
        for p in self._particles:
            p.t += p.speed * dt
            if p.t > 1.0:
                p.t -= 1.0
            elif p.t < 0.0:
                p.t += 1.0
            p.life += dt
            if p.life >= p.max_life:
                p.life = 0.0
                p.max_life = random.uniform(0.6, 2.0)
                p.t = random.random()
                p.offset = random.uniform(-0.4, 0.4)
                p.size = random.uniform(3.0, 9.0)
                p.speed = random.uniform(0.01, 0.04) * random.choice([-1, 1]) * self._flow_dir
                p._peak_alpha = random.uniform(0.04, 0.14)
                p._fade_in = random.uniform(0.2, 0.4)
                p._fade_out = random.uniform(0.2, 0.4)
            phase = p.life / p.max_life
            if phase < p._fade_in:
                fade = phase / p._fade_in
            elif phase > (1.0 - p._fade_out):
                fade = (1.0 - phase) / p._fade_out
            else:
                fade = 1.0
            p.alpha = fade * p._peak_alpha

    def paint(self, painter: QPainter, option, widget=None):
        if len(self._points) < 2:
            self._draw_handles(painter)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(self._width)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        river_clip = stroker.createStroke(self._path)
        # See _BasePathItem.shape() — a tight bend makes this outline
        # self-overlap, and the default OddEvenFill would punch a hole in
        # the clip exactly there (the terrain-colored sliver at a bend).
        river_clip.setFillRule(Qt.FillRule.WindingFill)

        # ── 1. Water body — texture along path or solid color ────────
        if self._texture and not self._texture.isNull():
            _draw_texture_along_path(
                painter, self._path, self._texture, self._width,
                tex_offset=self._tex_offset,
                clip_path=river_clip,
                owner=self,
                feather_px=max(2.0, min(10.0, self._width * 0.12)),
            )
        else:
            water_pen = QPen(QColor(60, 130, 180, 255), self._width)
            water_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            water_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(water_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._path)

        # ── 2. Minimal flow shimmer (very low alpha) ──────────────────
        if not self._path.isEmpty():
            painter.setPen(Qt.PenStyle.NoPen)
            for p in self._particles:
                if p.alpha < 0.01:
                    continue
                pt = self._path.pointAtPercent(max(0.0, min(1.0, p.t)))
                angle = self._path.angleAtPercent(max(0.0, min(1.0, p.t)))
                perp_rad = math.radians(angle + 90)
                lateral = p.offset * self._width * 0.35
                px = pt.x() + math.cos(perp_rad) * lateral
                py = pt.y() - math.sin(perp_rad) * lateral
                alpha = int(p.alpha * 180)
                grad = QRadialGradient(QPointF(px, py), p.size)
                grad.setColorAt(0.0, QColor(220, 240, 255, alpha))
                grad.setColorAt(1.0, QColor(220, 240, 255, 0))
                painter.setBrush(QBrush(grad))
                painter.drawEllipse(QPointF(px, py), p.size, p.size * 0.4)

        # ── 3. Center dashed line — only when selected ────────────────
        if self.isSelected():
            sel_pen = QPen(QColor(255, 255, 255, 90), 1.2, Qt.PenStyle.DashLine)
            sel_pen.setDashPattern([6, 5])
            sel_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._path)

        painter.restore()
        self._draw_handles(painter)


# ─── Road Path Item ──────────────────────────────────────────────────────────

class RoadPathItem(_BasePathItem):
    """Animated road: tiled road texture + dust puffs drifting off edges."""

    def __init__(self, width: float = 20.0, texture: QPixmap | None = None, parent=None):
        super().__init__(width, texture, parent)
        self.setZValue(8)
        self._spawn_particles()

    def _spawn_particles(self):
        self._particles = []
        for _ in range(random.randint(12, 22)):
            speed_range = random.uniform(0.001, 0.006)
            p = _Particle(
                t=random.random(),
                offset=random.uniform(-0.8, 0.8),
                alpha=0.0,
                size=random.uniform(1.0, 3.0),
                speed=random.uniform(speed_range * 0.5, speed_range),
            )
            p.max_life = random.uniform(0.4, 1.2)
            p.life = random.uniform(0.0, p.max_life)
            p._peak_alpha = random.uniform(0.5, 0.9)
            p._fade_in = random.uniform(0.2, 0.4)
            p._fade_out = random.uniform(0.2, 0.4)
            self._particles.append(p)

    def _update_particles(self):
        dt = self.ANIM_INTERVAL_MS / 1000.0
        for p in self._particles:
            p.t += p.speed * dt
            if p.t > 1.0:
                p.t -= 1.0
            p.life += dt
            if p.life >= p.max_life:
                p.life = 0.0
                p.max_life = random.uniform(0.4, 1.2)
                p.t = random.random()
                p.offset = random.uniform(-0.8, 0.8)
                p.size = random.uniform(1.0, 3.0)
                speed_range = random.uniform(0.001, 0.006)
                p.speed = random.uniform(speed_range * 0.5, speed_range)
                p._peak_alpha = random.uniform(0.5, 0.9)
                p._fade_in = random.uniform(0.2, 0.4)
                p._fade_out = random.uniform(0.2, 0.4)
            phase = p.life / p.max_life
            if phase < p._fade_in:
                fade = phase / p._fade_in
            elif phase > (1.0 - p._fade_out):
                fade = (1.0 - phase) / p._fade_out
            else:
                fade = 1.0
            p.alpha = fade * p._peak_alpha

    def paint(self, painter: QPainter, option, widget=None):
        if len(self._points) < 2:
            self._draw_handles(painter)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # ── 1. Road surface (texture along path or solid color) ───────
        if self._texture and not self._texture.isNull():
            # Clip stamps to the road stroke shape so they don't bleed outside
            from PySide6.QtGui import QPainterPathStroker
            stroker = QPainterPathStroker()
            stroker.setWidth(self._width)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            road_clip = stroker.createStroke(self._path)
            # See _BasePathItem.shape() — a tight bend makes this outline
            # self-overlap, and the default OddEvenFill would punch a hole
            # in the clip exactly there.
            road_clip.setFillRule(Qt.FillRule.WindingFill)
            _draw_texture_along_path(
                painter, self._path, self._texture, self._width,
                clip_path=road_clip,
                owner=self,
                feather_px=max(2.0, min(10.0, self._width * 0.12)),
            )
        else:
            road_pen = QPen(QColor(139, 119, 85, 230), self._width)
            road_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            road_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(road_pen)
            painter.drawPath(self._path)

        # ── 3. Center line (dashed) — only when editing or selected
        if self.isSelected():
            t = time.monotonic()
            dash_offset = (t * 20.0) % 30.0
            center_pen = QPen(QColor(255, 255, 200, 90), 1.5, Qt.PenStyle.DashLine)
            center_pen.setDashOffset(dash_offset)
            center_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(center_pen)
            painter.drawPath(self._path)

        # ── 4. Dust particles drifting off road edges ─────────────────
        if not self._path.isEmpty():
            painter.setPen(Qt.PenStyle.NoPen)
            for p in self._particles:
                if p.alpha < 0.04:
                    continue
                pt = self._path.pointAtPercent(max(0.0, min(1.0, p.t)))
                angle = self._path.angleAtPercent(max(0.0, min(1.0, p.t)))
                perp_rad = math.radians(angle + 90)
                lateral = p.offset * self._width * 0.5
                px = pt.x() + math.cos(perp_rad) * lateral
                py = pt.y() - math.sin(perp_rad) * lateral
                alpha = int(p.alpha * 220)
                dust_color = QColor(210, 190, 150, alpha)
                grad = QRadialGradient(QPointF(px, py), p.size)
                grad.setColorAt(0.0, dust_color)
                grad.setColorAt(1.0, QColor(210, 190, 150, 0))
                painter.setBrush(QBrush(grad))
                painter.drawEllipse(QPointF(px, py), p.size, p.size * 0.45)



        painter.restore()
        self._draw_handles(painter)
