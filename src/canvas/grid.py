"""Grid Manager — configurable grid overlay with multiple cell shapes."""

from __future__ import annotations

import math

from PySide6.QtWidgets import QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem, QGraphicsPathItem, QGraphicsSimpleTextItem
from PySide6.QtCore import Qt, QRectF, QLineF, QPointF
from PySide6.QtGui import QPen, QColor, QPainterPath, QFont, QPolygonF

from src.canvas.overlays.scale_bar import format_distance


class GridShape:
    NONE = "Nenhum"
    SQUARE = "Quadrado"
    HEXAGON = "Hex\u00e1gono"
    TRIANGLE = "Tri\u00e2ngulo"
    DIAMOND = "Losango"
    ISOMETRIC = "Isom\u00e9trico"


class _ClippedGroup(QGraphicsItemGroup):
    """Grid item group that clips its children to an arbitrary path.

    Used to conform the grid to a bounded terrain's exact boundary shape
    (circle, hexagon, ...), not just its rectangular bounding box.
    """

    def __init__(self):
        super().__init__()
        self._clip_path = QPainterPath()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

    def set_clip_path(self, path: QPainterPath | None):
        self.prepareGeometryChange()
        self._clip_path = path if path is not None else QPainterPath()

    def shape(self) -> QPainterPath:
        if self._clip_path.isEmpty():
            return super().shape()
        return self._clip_path

    def boundingRect(self) -> QRectF:
        if self._clip_path.isEmpty():
            return super().boundingRect()
        return self._clip_path.boundingRect()

    def contains(self, point) -> bool:
        # shape() above is the full terrain outline — needed so
        # ItemClipsChildrenToShape clips grid lines correctly, but it must
        # NOT make the (invisible) filled interior hit-testable, or clicks
        # over ungrid-drawn areas get swallowed by this decorative overlay
        # instead of reaching the select/pan tools underneath.
        return False


class GridManager:
    """Draws and manages a configurable grid on the scene."""

    LABEL_MIN_SPACING_PX = 60  # min on-screen gap between coordinate labels

    def __init__(self, scene):
        self._scene = scene
        self._group: QGraphicsItemGroup | None = None
        self._measure_group: QGraphicsItemGroup | None = None

        # Config — 1 scene unit == 1 meter (see scale_bar.py), so subdivisions
        # finer than whole meters aren't meaningful; max_subdivisions() below
        # is the hard cap that keeps that true regardless of cell_size.
        self.cell_size = 100
        self.subdivisions = 1
        self.shape = GridShape.SQUARE
        self.color_major = QColor(255, 255, 255, 80)
        self.color_minor = QColor(255, 255, 255, 35)
        self.color_axis = QColor(79, 195, 247, 200)  # accent — marks x=0 / y=0
        self.visible = True
        # Cartesian x=0/y=0 axis lines + meter labels — independent of shape,
        # so it can overlay hexagon/triangle/diamond/isometric grids too.
        self.show_measurements = False

    def set_visible(self, visible: bool):
        self.visible = visible
        if self._group:
            self._group.setVisible(visible)

    def toggle(self):
        self.set_visible(not self.visible)

    def max_subdivisions(self) -> int:
        """Highest subdivision count that still keeps each sub-cell >= 1 meter."""
        return max(1, int(self.cell_size))

    def _clamped_subdivisions(self) -> int:
        return max(1, min(int(self.subdivisions), self.max_subdivisions()))

    def update(
        self, view_rect: QRectF, zoom: float = 1.0,
        clip_path: QPainterPath | None = None, full_view_rect: QRectF | None = None,
    ):
        """Redraw grid for the visible area.

        `zoom` (screen px per scene unit) is only used by the Square shape, to
        space out coordinate labels and keep their on-screen text size constant.
        `clip_path` (scene coordinates), when given, conforms the grid to a
        bounded terrain's exact boundary shape instead of a rectangle.
        `view_rect` may already be narrowed to a bounded terrain's extent —
        `full_view_rect` (defaults to `view_rect` itself) is the actual
        on-screen viewport, used for the measurement ruler so it keeps
        growing with the pan instead of stopping at the terrain's edge.
        """
        self._clear()
        # `visible` gates the shape lines only (it's driven by the shape
        # dropdown — "Nenhum" = off) — measurements are an independent
        # overlay and must still be able to render with no shape selected.
        if not self.visible and not self.show_measurements:
            return

        self._group = _ClippedGroup()
        self._group.setZValue(-1000)
        self._group.set_clip_path(clip_path)

        if self.visible:
            if self.shape == GridShape.NONE:
                pass
            elif self.shape == GridShape.SQUARE:
                self._draw_square(view_rect)
            elif self.shape == GridShape.HEXAGON:
                self._draw_hexagon(view_rect)
            elif self.shape == GridShape.TRIANGLE:
                self._draw_triangle(view_rect)
            elif self.shape == GridShape.DIAMOND:
                self._draw_diamond(view_rect)
            elif self.shape == GridShape.ISOMETRIC:
                self._draw_isometric(view_rect)

        self._scene.addItem(self._group)

        if self.show_measurements:
            # Own, unclipped group — measurements are a coordinate ruler for
            # the whole (effectively infinite) map, not just whatever shape
            # a bounded terrain's grid conforms to, so they must keep
            # growing with the pan regardless of `clip_path`.
            self._measure_group = QGraphicsItemGroup()
            self._measure_group.setZValue(-999)
            self._draw_cartesian_overlay(full_view_rect if full_view_rect is not None else view_rect, zoom)
            self._scene.addItem(self._measure_group)

    # ─── Cartesian overlay (x=0/y=0 axis + meter labels) ──────────────────
    # Independent of shape — toggled on its own via show_measurements, so it
    # can sit on top of hexagon/triangle/diamond/isometric grids too, not
    # just Square.

    def _draw_cartesian_overlay(self, view_rect: QRectF, zoom: float):
        pen_axis = QPen(self.color_axis, 2)
        pen_axis.setCosmetic(True)

        if view_rect.left() <= 0 <= view_rect.right():
            line = QGraphicsLineItem(QLineF(0, view_rect.top(), 0, view_rect.bottom()))
            line.setPen(pen_axis)
            self._measure_group.addToGroup(line)

        if view_rect.top() <= 0 <= view_rect.bottom():
            line = QGraphicsLineItem(QLineF(view_rect.left(), 0, view_rect.right(), 0))
            line.setPen(pen_axis)
            self._measure_group.addToGroup(line)

        self._draw_square_labels(view_rect, zoom)

    # ─── Square ─────────────────────────────────────────────────────────

    def _draw_square(self, view_rect: QRectF):
        pen_major = QPen(self.color_major, 1)
        pen_major.setCosmetic(True)
        pen_minor = QPen(self.color_minor, 1)
        pen_minor.setCosmetic(True)

        sub_size = self.cell_size / self._clamped_subdivisions()
        left = int(view_rect.left() / sub_size) * sub_size
        top = int(view_rect.top() / sub_size) * sub_size

        x = left
        while x <= view_rect.right():
            is_major = abs(x % self.cell_size) < 0.01
            line = QGraphicsLineItem(QLineF(x, view_rect.top(), x, view_rect.bottom()))
            line.setPen(pen_major if is_major else pen_minor)
            self._group.addToGroup(line)
            x += sub_size

        y = top
        while y <= view_rect.bottom():
            is_major = abs(y % self.cell_size) < 0.01
            line = QGraphicsLineItem(QLineF(view_rect.left(), y, view_rect.right(), y))
            line.setPen(pen_major if is_major else pen_minor)
            self._group.addToGroup(line)
            y += sub_size

    # Minimum on-screen gap a tier of labels needs before it's skipped —
    # majors get the full spacing, subdivisions (denser, so more crowded)
    # get a smaller floor since they're dimmer and less likely to collide
    # meaningfully.
    SUBDIVISION_LABEL_MIN_SPACING_PX = 28

    def _draw_square_labels(self, view_rect: QRectF, zoom: float):
        if zoom <= 0:
            return
        major_step = self.cell_size
        if major_step <= 0:
            return
        sub_step = major_step / self._clamped_subdivisions()

        inv_scale = 1.0 / zoom
        pad = 3 * inv_scale
        font_major = QFont("Segoe UI", 8)
        font_minor = QFont("Segoe UI", 7)

        def _label(text: str, sx: float, sy: float, brush: QColor, font: QFont):
            item = QGraphicsSimpleTextItem(text)
            item.setFont(font)
            item.setBrush(brush)
            item.setScale(inv_scale)
            item.setZValue(2)
            item.setPos(sx, sy)
            self._measure_group.addToGroup(item)

        # Labels ride the actual x=0 / y=0 axis lines, clamped to stay on
        # screen when the origin itself is scrolled out of view.
        axis_y = max(view_rect.top(), min(0.0, view_rect.bottom())) + pad
        axis_x = max(view_rect.left(), min(0.0, view_rect.right())) + pad

        # Same tone the grid lines use for major/minor — ties the ruler's
        # emphasis and the Opacity slider together, same as the grid itself.
        major_brush = QColor(self.color_major)
        major_brush.setAlpha(min(255, self.color_major.alpha() + 80))
        minor_brush = QColor(self.color_minor)
        minor_brush.setAlpha(min(255, self.color_minor.alpha() + 60))

        show_major = major_step * zoom >= self.LABEL_MIN_SPACING_PX
        # No point drawing subdivision ticks that coincide with a major one,
        # nor drawing them at all when there's only one subdivision (cell
        # size itself would be relabeled as "sub").
        show_minor = (
            self._clamped_subdivisions() > 1
            and sub_step * zoom >= self.SUBDIVISION_LABEL_MIN_SPACING_PX
        )

        def _is_major(v: float) -> bool:
            return abs(v % major_step) < 0.01 or abs(v % major_step - major_step) < 0.01

        if show_major or show_minor:
            step = sub_step if show_minor else major_step
            x = math.floor(view_rect.left() / step) * step
            while x <= view_rect.right():
                if abs(x) > 0.01:  # origin labeled once, at the axis crossing below
                    major = _is_major(x)
                    if major and show_major:
                        _label(format_distance(x), x + pad, axis_y, major_brush, font_major)
                    elif not major and show_minor:
                        _label(format_distance(x, decimals=1), x + pad, axis_y, minor_brush, font_minor)
                x += step

            y = math.floor(view_rect.top() / step) * step
            while y <= view_rect.bottom():
                if abs(y) > 0.01:
                    major = _is_major(y)
                    # Scene Y grows downward — flip the displayed label so it
                    # reads growing upward (north-positive), while the tick's
                    # actual on-screen position stays at the real scene y.
                    if major and show_major:
                        _label(format_distance(-y), axis_x, y + pad, major_brush, font_major)
                    elif not major and show_minor:
                        _label(format_distance(-y, decimals=1), axis_x, y + pad, minor_brush, font_minor)
                y += step

        if view_rect.contains(QPointF(0, 0)):
            _label("0", axis_x, axis_y, major_brush, font_major)

    # ─── Hexagon (flat-top honeycomb) ─────────────────────────────────

    def _draw_hexagon(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size / 2  # radius (center to vertex)
        w = s * 2              # hex width
        h = s * math.sqrt(3)   # hex height
        col_step = w * 0.75    # horizontal distance between centers
        row_step = h           # vertical distance between centers

        col_start = int(view_rect.left() / col_step) - 1
        col_end = int(view_rect.right() / col_step) + 2
        row_start = int(view_rect.top() / row_step) - 1
        row_end = int(view_rect.bottom() / row_step) + 2

        for col in range(col_start, col_end):
            for row in range(row_start, row_end):
                cx = col * col_step
                cy = row * row_step + (row_step * 0.5 if col % 2 else 0)
                path = self._hex_path(cx, cy, s)
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self._group.addToGroup(item)

    def _hex_path(self, cx: float, cy: float, radius: float) -> QPainterPath:
        """Flat-top hexagon path."""
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i)  # flat-top: starts at 0°
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        return path

    # ─── Triangle ────────────────────────────────────────────────────────

    def _draw_triangle(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        h = s * math.sqrt(3) / 2

        col_start = int(view_rect.left() / (s / 2)) - 1
        col_end = int(view_rect.right() / (s / 2)) + 2
        row_start = int(view_rect.top() / h) - 1
        row_end = int(view_rect.bottom() / h) + 2

        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                x = col * (s / 2)
                y = row * h
                up = (col + row) % 2 == 0
                path = QPainterPath()
                if up:
                    path.moveTo(x, y + h)
                    path.lineTo(x + s / 2, y)
                    path.lineTo(x + s, y + h)
                else:
                    path.moveTo(x, y)
                    path.lineTo(x + s / 2, y + h)
                    path.lineTo(x + s, y)
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self._group.addToGroup(item)

    # ─── Diamond ─────────────────────────────────────────────────────────

    def _draw_diamond(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        half = s / 2

        col_start = int(view_rect.left() / s) - 1
        col_end = int(view_rect.right() / s) + 2
        row_start = int(view_rect.top() / s) - 1
        row_end = int(view_rect.bottom() / s) + 2

        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                cx = col * s + (half if row % 2 else 0)
                cy = row * half
                path = QPainterPath()
                path.moveTo(cx, cy - half)
                path.lineTo(cx + half, cy)
                path.lineTo(cx, cy + half)
                path.lineTo(cx - half, cy)
                path.closeSubpath()
                item = QGraphicsPathItem(path)
                item.setPen(pen)
                self._group.addToGroup(item)

    # ─── Isometric ───────────────────────────────────────────────────────

    def _draw_isometric(self, view_rect: QRectF):
        pen = QPen(self.color_major, 1)
        pen.setCosmetic(True)

        s = self.cell_size
        # Diagonal lines at 30° (rise = s/2 for every run = s)
        left = view_rect.left()
        right = view_rect.right()
        top = view_rect.top()
        bottom = view_rect.bottom()
        span = right - left + bottom - top

        # Lines going top-left to bottom-right (\)
        start = int((left + top) / s) * s - int(span / s) * s
        end = int((right + bottom) / s) * s + s
        offset = start
        while offset <= end:
            x1 = offset - top
            x2 = offset - bottom
            line = QGraphicsLineItem(QLineF(x1, top, x2, bottom))
            line.setPen(pen)
            self._group.addToGroup(line)
            offset += s

        # Lines going top-right to bottom-left (/)
        start = int((left - bottom) / s) * s - s
        end = int((right - top) / s) * s + int(span / s) * s
        offset = start
        while offset <= end:
            x1 = offset + top
            x2 = offset + bottom
            line = QGraphicsLineItem(QLineF(x1, top, x2, bottom))
            line.setPen(pen)
            self._group.addToGroup(line)
            offset += s

    # ─── Common ──────────────────────────────────────────────────────────

    def _clear(self):
        if self._group:
            self._scene.removeItem(self._group)
            self._group = None
        if self._measure_group:
            self._scene.removeItem(self._measure_group)
            self._measure_group = None

    def snap(self, x: float, y: float) -> tuple[float, float]:
        """Snap coordinates to nearest grid intersection."""
        sx = round(x / self.cell_size) * self.cell_size
        sy = round(y / self.cell_size) * self.cell_size
        return sx, sy

    def snap_sub(self, x: float, y: float) -> tuple[float, float]:
        """Snap to the active shape's cell lattice.

        Used by SnapManager to snap brush stroke positions — with Snap on,
        a stamp's center lands on the nearest square sub-cell, hex center,
        triangle-lattice vertex, diamond center, or isometric intersection,
        matching whichever grid shape is currently selected.
        """
        if self.shape == GridShape.NONE:
            return x, y
        if self.shape == GridShape.HEXAGON:
            return self._snap_hexagon(x, y)
        if self.shape == GridShape.TRIANGLE:
            return self._snap_triangle(x, y)
        if self.shape == GridShape.DIAMOND:
            return self._snap_diamond(x, y)
        if self.shape == GridShape.ISOMETRIC:
            return self._snap_isometric(x, y)

        sub = self.cell_size / self._clamped_subdivisions()
        sx = round(x / sub) * sub
        sy = round(y / sub) * sub
        return sx, sy

    def _snap_hexagon(self, x: float, y: float) -> tuple[float, float]:
        s = self.cell_size / 2
        w = s * 2
        h = s * math.sqrt(3)
        col_step = w * 0.75
        row_step = h

        col_f = x / col_step
        best = None
        best_d = None
        for col in (math.floor(col_f), math.ceil(col_f)):
            row_offset = row_step * 0.5 if col % 2 else 0
            row_f = (y - row_offset) / row_step
            for row in (math.floor(row_f), math.ceil(row_f)):
                cx = col * col_step
                cy = row * row_step + row_offset
                d = (cx - x) ** 2 + (cy - y) ** 2
                if best_d is None or d < best_d:
                    best_d, best = d, (cx, cy)
        return best

    def _snap_triangle(self, x: float, y: float) -> tuple[float, float]:
        """Snaps to the triangular lattice's vertices (where edges meet)."""
        s = self.cell_size
        h = s * math.sqrt(3) / 2
        half = s / 2
        return round(x / half) * half, round(y / h) * h

    def _snap_diamond(self, x: float, y: float) -> tuple[float, float]:
        s = self.cell_size
        half = s / 2

        row_f = y / half
        best = None
        best_d = None
        for row in (math.floor(row_f), math.ceil(row_f)):
            col_offset = half if row % 2 else 0
            col_f = (x - col_offset) / s
            for col in (math.floor(col_f), math.ceil(col_f)):
                cx = col * s + col_offset
                cy = row * half
                d = (cx - x) ** 2 + (cy - y) ** 2
                if best_d is None or d < best_d:
                    best_d, best = d, (cx, cy)
        return best

    def _snap_isometric(self, x: float, y: float) -> tuple[float, float]:
        """Snaps to intersections of the \\ and / line families.

        Points on a '\\' line keep x+y constant; points on a '/' line keep
        x-y constant (see _draw_isometric) — so rounding those two sums to
        the nearest multiple of cell_size and solving back for x/y lands
        exactly on a line intersection.
        """
        s = self.cell_size
        k = round((x + y) / s)
        m = round((x - y) / s)
        return (k + m) * s / 2, (k - m) * s / 2

    # ─── Cell boundary (whole-cell paint fill when Snap is on) ────────────

    def cell_polygon(self, x: float, y: float) -> QPolygonF | None:
        """Boundary of whichever cell contains scene point (x, y), in the
        active shape. None for GridShape.NONE (nothing to fill).

        Used by BrushTool when Snap is enabled: instead of a soft circular
        stamp, the whole cell you clicked in gets filled solid — this is
        what finds that cell's exact outline.
        """
        if self.shape == GridShape.SQUARE:
            return self._cell_square(x, y)
        if self.shape == GridShape.HEXAGON:
            return self._cell_hexagon(x, y)
        if self.shape == GridShape.TRIANGLE:
            return self._cell_triangle(x, y)
        if self.shape == GridShape.DIAMOND:
            return self._cell_diamond(x, y)
        if self.shape == GridShape.ISOMETRIC:
            return self._cell_isometric(x, y)
        return None

    def _cell_square(self, x: float, y: float) -> QPolygonF:
        sub = self.cell_size / self._clamped_subdivisions()
        left = math.floor(x / sub) * sub
        top = math.floor(y / sub) * sub
        return QPolygonF([
            QPointF(left, top), QPointF(left + sub, top),
            QPointF(left + sub, top + sub), QPointF(left, top + sub),
        ])

    def _cell_hexagon(self, x: float, y: float) -> QPolygonF:
        s = self.cell_size / 2
        cx, cy = self._snap_hexagon(x, y)
        path = self._hex_path(cx, cy, s)
        return path.toFillPolygon()

    def _cell_triangle(self, x: float, y: float) -> QPolygonF:
        """_draw_triangle's (col, row) each only cover a slim wedge near
        their own apex, not a clean rect — floor(x/(s/2)) alone can land one
        column off from the triangle that actually contains the point. Check
        the col/row neighborhood and keep whichever candidate really
        contains (x, y), same safety net as the hex/diamond nearest-center
        search above."""
        s = self.cell_size
        h = s * math.sqrt(3) / 2
        col0 = math.floor(x / (s / 2))
        row0 = math.floor(y / h)
        pt = QPointF(x, y)
        for row in (row0 - 1, row0, row0 + 1):
            for col in (col0 - 1, col0, col0 + 1):
                cx = col * (s / 2)
                cy = row * h
                if (col + row) % 2 == 0:
                    poly = QPolygonF([QPointF(cx, cy + h), QPointF(cx + s / 2, cy), QPointF(cx + s, cy + h)])
                else:
                    poly = QPolygonF([QPointF(cx, cy), QPointF(cx + s / 2, cy + h), QPointF(cx + s, cy)])
                if poly.containsPoint(pt, Qt.FillRule.OddEvenFill):
                    return poly
        # Shouldn't happen (the 3x3 neighborhood always covers the point) —
        # fall back to the naive guess rather than returning nothing.
        cx, cy = col0 * (s / 2), row0 * h
        if (col0 + row0) % 2 == 0:
            return QPolygonF([QPointF(cx, cy + h), QPointF(cx + s / 2, cy), QPointF(cx + s, cy + h)])
        return QPolygonF([QPointF(cx, cy), QPointF(cx + s / 2, cy + h), QPointF(cx + s, cy)])

    def _cell_diamond(self, x: float, y: float) -> QPolygonF:
        s = self.cell_size
        half = s / 2
        cx, cy = self._snap_diamond(x, y)
        return QPolygonF([
            QPointF(cx, cy - half), QPointF(cx + half, cy),
            QPointF(cx, cy + half), QPointF(cx - half, cy),
        ])

    def _cell_isometric(self, x: float, y: float) -> QPolygonF:
        """The \\ and / line families (see _draw_isometric) form a regular
        square grid in (u,v) = (x+y, x-y) space — floor-dividing there finds
        the cell directly, no nearest-neighbor search needed, same trick as
        _snap_isometric but one level up (a cell instead of a vertex)."""
        s = self.cell_size
        u, v = x + y, x - y
        k = math.floor(u / s)
        m = math.floor(v / s)
        corners_uv = [(k * s, m * s), ((k + 1) * s, m * s), ((k + 1) * s, (m + 1) * s), (k * s, (m + 1) * s)]
        return QPolygonF([QPointF((uu + vv) / 2, (uu - vv) / 2) for uu, vv in corners_uv])
