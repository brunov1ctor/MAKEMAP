"""TerrainFreehandTool — click-to-place-point polygon drawing for a "Livre"
terreno boundary.

Armed by TerrainEditPanel's "Livre" shape button (not a tool a user picks
from the main toolbar) — each left click on canvas adds a point;
TerrainMediator rebuilds the pending terreno's MapBoundary after every
point so the shape reads as "under construction" instead of only
appearing once finished. Clicking "Livre" again closes the polygon.

Snap + live measurement (CAD-style "polar snap" + dynamic distance/angle
readout): each new point snaps to the grid (when Snap is enabled) and,
independently, to the nearest 15° increment from the previous point
whenever the raw angle is already close to one — same "magnetic" feel as
professional 2D drafting tools, without forcing every segment onto a
15° multiple.

Point interaction: pressing down ON the most-recently-placed point (within
DRAG_HIT_TOLERANCE) and dragging repositions it live instead of adding a
new point — lets a corner/angle just placed be nudged into place without
undoing and re-clicking it. Only the LAST point is ever draggable, kept
that way deliberately: editing an EARLIER point's position would ripple
into segments TerrainMediator has already spliced/persisted state around.

Curve editing: right-click-dragging bows the MOST RECENTLY completed
segment (the one just before the last point) into a quadratic curve, with
the drag position as the Bézier control point. Only ever affects that one
latest segment — same "only the newest thing is editable" rule as point
dragging, for the same reason (older segments may already be spliced into
an existing shape by insert-mode, where segment indices don't map
1:1 to a simple curve list once merged — see TerrainMediator).
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent

from src.canvas.tools.base import BaseTool

ANGLE_SNAP_DEG = 15.0
ANGLE_SNAP_TOLERANCE_DEG = 4.0
DRAG_HIT_TOLERANCE = 30.0  # scene units — how close a press must land to the last point to grab it


class TerrainFreehandTool(BaseTool):
    name = "TerrenoLivre"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, viewport):
        super().__init__(viewport)
        self._points: list[QPointF] = []
        self._snap_manager = None
        self._dragging = False
        self._curve_controls: dict[int, QPointF] = {}  # segment start index -> control point
        self._curve_dragging_segment: int | None = None
        # Plain callbacks, not Signals — BaseTool isn't a QObject (same
        # convention as MapBoundary.on_moved / BrushTool.on_bounds_missing).
        self.on_point_added = None      # callable(points: list[QPointF]) — a NEW point was placed
        self.on_point_moved = None      # callable(points: list[QPointF]) — the LAST point's position changed
        self.on_preview_changed = None  # callable(points, preview_pos, distance_m | None, angle_deg | None)
        self.on_curve_changed = None    # callable(segment_index: int, control: QPointF)
        self.on_escape = None           # callable() — Esc pressed while drawing

    def set_snap_manager(self, snap_manager):
        self._snap_manager = snap_manager

    def activate(self):
        super().activate()
        self._points = []
        self._dragging = False
        self._curve_controls = {}
        self._curve_dragging_segment = None

    def deactivate(self):
        super().deactivate()
        self._points = []
        self._dragging = False
        self._curve_controls = {}
        self._curve_dragging_segment = None

    def _snap_pos(self, pos: QPointF, reference: QPointF | None = None) -> QPointF:
        if self._snap_manager:
            pos = self._snap_manager.snap(pos)
        if reference is not None:
            pos = self._angle_snap(reference, pos)
        return pos

    def _angle_snap(self, origin: QPointF, pos: QPointF) -> QPointF:
        dx, dy = pos.x() - origin.x(), pos.y() - origin.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return pos
        angle = math.degrees(math.atan2(dy, dx))
        nearest = round(angle / ANGLE_SNAP_DEG) * ANGLE_SNAP_DEG
        # Shortest signed angular difference, so the 359°/0° wraparound
        # doesn't read as a huge gap and skip the snap right at the seam.
        diff = (angle - nearest + 180) % 360 - 180
        if abs(diff) <= ANGLE_SNAP_TOLERANCE_DEG:
            rad = math.radians(nearest)
            return QPointF(origin.x() + dist * math.cos(rad), origin.y() + dist * math.sin(rad))
        return pos

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF):
        if event.button() == Qt.MouseButton.RightButton:
            # Bows the most recently completed segment into a curve — only
            # possible once at least two points exist (one full segment).
            if len(self._points) >= 2:
                self._curve_dragging_segment = len(self._points) - 2
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        raw = QPointF(scene_pos)
        if self._points:
            last = self._points[-1]
            if math.hypot(raw.x() - last.x(), raw.y() - last.y()) <= DRAG_HIT_TOLERANCE:
                # Grabbed the last point — whether this becomes an actual
                # move only resolves in mouse_move; a plain click-release
                # right here with no drag is treated as a no-op, not a
                # redundant duplicate point at the same spot.
                self._dragging = True
                return
        reference = self._points[-1] if self._points else None
        pos = self._snap_pos(raw, reference)
        self._points.append(pos)
        if self.on_point_added:
            self.on_point_added(list(self._points))

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF):
        if self._curve_dragging_segment is not None:
            control = QPointF(scene_pos)
            self._curve_controls[self._curve_dragging_segment] = control
            if self.on_curve_changed:
                self.on_curve_changed(self._curve_dragging_segment, control)
            return
        if self._dragging and self._points:
            # Angle-snap relative to the point BEFORE the one being
            # dragged — snapping relative to itself would always measure
            # zero distance.
            reference = self._points[-2] if len(self._points) >= 2 else None
            pos = self._snap_pos(QPointF(scene_pos), reference)
            self._points[-1] = pos
            if self.on_point_moved:
                self.on_point_moved(list(self._points))
            return
        if not self.on_preview_changed:
            return
        reference = self._points[-1] if self._points else None
        pos = self._snap_pos(QPointF(scene_pos), reference)
        distance_m = None
        angle_deg = None
        if self._points:
            last = self._points[-1]
            dx, dy = pos.x() - last.x(), pos.y() - last.y()
            distance_m = math.hypot(dx, dy)
            # Screen/scene Y grows downward; flip so the reading matches
            # the grid ruler's upward-growing north, same convention as
            # MainLayout's own coordinate display.
            angle_deg = math.degrees(math.atan2(-dy, dx)) % 360
        self.on_preview_changed(list(self._points), pos, distance_m, angle_deg)

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF):
        self._dragging = False
        self._curve_dragging_segment = None

    def key_press(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self.on_escape:
            self.on_escape()

    @property
    def points(self) -> list[QPointF]:
        return list(self._points)

    @property
    def curve_controls(self) -> dict[int, QPointF]:
        return dict(self._curve_controls)
