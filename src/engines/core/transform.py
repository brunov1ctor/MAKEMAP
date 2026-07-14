"""Transform Engine — independent spatial transformation system."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem
from PySide6.QtGui import QPen, QColor, QTransform


class HandleType(Enum):
    TOP_LEFT = auto()
    TOP_CENTER = auto()
    TOP_RIGHT = auto()
    MIDDLE_LEFT = auto()
    MIDDLE_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_CENTER = auto()
    BOTTOM_RIGHT = auto()
    ROTATION = auto()


class AlignMode(Enum):
    LEFT = auto()
    CENTER_H = auto()
    RIGHT = auto()
    TOP = auto()
    CENTER_V = auto()
    BOTTOM = auto()


class DistributeMode(Enum):
    HORIZONTAL = auto()
    VERTICAL = auto()


class TransformEngine(QObject):
    """Manages all spatial transformations for selected items."""

    transform_started = Signal()
    transform_finished = Signal()
    items_moved = Signal(list, float, float)  # items, dx, dy

    HANDLE_SIZE = 8

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._handles: list[QGraphicsRectItem] = []
        self._rotation_handle: QGraphicsEllipseItem | None = None
        self._active_handle: HandleType | None = None
        self._transform_origin = QPointF()
        self._initial_positions: dict[QGraphicsItem, QPointF] = {}
        self._initial_transforms: dict[QGraphicsItem, QTransform] = {}

    # --- Move ---

    def move(self, items: list[QGraphicsItem], dx: float, dy: float):
        """Move items by delta."""
        for item in items:
            item.moveBy(dx, dy)
        self.items_moved.emit(items, dx, dy)

    def move_to(self, items: list[QGraphicsItem], x: float, y: float):
        """Move items so that the bounding rect top-left is at (x, y)."""
        if not items:
            return
        bounds = self._get_bounds(items)
        dx = x - bounds.x()
        dy = y - bounds.y()
        self.move(items, dx, dy)

    # --- Rotate ---

    def rotate(self, items: list[QGraphicsItem], angle: float, center: QPointF | None = None):
        """Rotate items around a center point."""
        if not items:
            return
        if center is None:
            center = self._get_bounds(items).center()

        for item in items:
            # Rotate around center
            item_center = item.sceneBoundingRect().center()
            offset = item_center - center

            t = QTransform()
            t.translate(center.x(), center.y())
            t.rotate(angle)
            t.translate(-center.x(), -center.y())

            new_pos = t.map(item.pos())
            item.setPos(new_pos)
            item.setRotation(item.rotation() + angle)

    # --- Scale ---

    def scale(self, items: list[QGraphicsItem], sx: float, sy: float, center: QPointF | None = None):
        """Scale items relative to a center point."""
        if not items:
            return
        if center is None:
            center = self._get_bounds(items).center()

        for item in items:
            # Scale position relative to center
            pos = item.pos()
            new_x = center.x() + (pos.x() - center.x()) * sx
            new_y = center.y() + (pos.y() - center.y()) * sy
            item.setPos(new_x, new_y)

            current = item.transform()
            t = QTransform()
            t.scale(sx, sy)
            item.setTransform(current * t)

    def scale_uniform(self, items: list[QGraphicsItem], factor: float, center: QPointF | None = None):
        """Scale uniformly (proportional)."""
        self.scale(items, factor, factor, center)

    # --- Flip ---

    def flip_horizontal(self, items: list[QGraphicsItem]):
        """Flip items horizontally around their combined center."""
        if not items:
            return
        center = self._get_bounds(items).center()
        for item in items:
            pos = item.pos()
            new_x = center.x() + (center.x() - pos.x())
            item.setPos(new_x, pos.y())

            current = item.transform()
            t = QTransform()
            t.scale(-1, 1)
            item.setTransform(current * t)

    def flip_vertical(self, items: list[QGraphicsItem]):
        """Flip items vertically around their combined center."""
        if not items:
            return
        center = self._get_bounds(items).center()
        for item in items:
            pos = item.pos()
            new_y = center.y() + (center.y() - pos.y())
            item.setPos(pos.x(), new_y)

            current = item.transform()
            t = QTransform()
            t.scale(1, -1)
            item.setTransform(current * t)

    # --- Align ---

    def align(self, items: list[QGraphicsItem], mode: AlignMode):
        """Align items to a common edge or center."""
        if len(items) < 2:
            return

        bounds = self._get_bounds(items)

        for item in items:
            rect = item.sceneBoundingRect()
            pos = item.pos()

            if mode == AlignMode.LEFT:
                item.setPos(pos.x() + (bounds.left() - rect.left()), pos.y())
            elif mode == AlignMode.CENTER_H:
                item.setPos(pos.x() + (bounds.center().x() - rect.center().x()), pos.y())
            elif mode == AlignMode.RIGHT:
                item.setPos(pos.x() + (bounds.right() - rect.right()), pos.y())
            elif mode == AlignMode.TOP:
                item.setPos(pos.x(), pos.y() + (bounds.top() - rect.top()))
            elif mode == AlignMode.CENTER_V:
                item.setPos(pos.x(), pos.y() + (bounds.center().y() - rect.center().y()))
            elif mode == AlignMode.BOTTOM:
                item.setPos(pos.x(), pos.y() + (bounds.bottom() - rect.bottom()))

    # --- Distribute ---

    def distribute(self, items: list[QGraphicsItem], mode: DistributeMode):
        """Distribute items evenly along an axis."""
        if len(items) < 3:
            return

        if mode == DistributeMode.HORIZONTAL:
            sorted_items = sorted(items, key=lambda i: i.sceneBoundingRect().center().x())
            first_center = sorted_items[0].sceneBoundingRect().center().x()
            last_center = sorted_items[-1].sceneBoundingRect().center().x()
            spacing = (last_center - first_center) / (len(sorted_items) - 1)

            for i, item in enumerate(sorted_items[1:-1], start=1):
                target_x = first_center + spacing * i
                current_x = item.sceneBoundingRect().center().x()
                item.moveBy(target_x - current_x, 0)

        elif mode == DistributeMode.VERTICAL:
            sorted_items = sorted(items, key=lambda i: i.sceneBoundingRect().center().y())
            first_center = sorted_items[0].sceneBoundingRect().center().y()
            last_center = sorted_items[-1].sceneBoundingRect().center().y()
            spacing = (last_center - first_center) / (len(sorted_items) - 1)

            for i, item in enumerate(sorted_items[1:-1], start=1):
                target_y = first_center + spacing * i
                current_y = item.sceneBoundingRect().center().y()
                item.moveBy(0, target_y - current_y)

    # --- Handles ---

    def show_handles(self, items: list[QGraphicsItem]):
        """Show transform handles around the selection bounding rect."""
        self.hide_handles()
        if not items:
            return

        bounds = self._get_bounds(items)
        s = self.HANDLE_SIZE
        pen = QPen(QColor(79, 195, 247), 1.5)
        brush = QColor(79, 195, 247, 200)

        positions = {
            HandleType.TOP_LEFT: bounds.topLeft(),
            HandleType.TOP_CENTER: QPointF(bounds.center().x(), bounds.top()),
            HandleType.TOP_RIGHT: bounds.topRight(),
            HandleType.MIDDLE_LEFT: QPointF(bounds.left(), bounds.center().y()),
            HandleType.MIDDLE_RIGHT: QPointF(bounds.right(), bounds.center().y()),
            HandleType.BOTTOM_LEFT: bounds.bottomLeft(),
            HandleType.BOTTOM_CENTER: QPointF(bounds.center().x(), bounds.bottom()),
            HandleType.BOTTOM_RIGHT: bounds.bottomRight(),
        }

        for handle_type, pos in positions.items():
            handle = QGraphicsRectItem(pos.x() - s / 2, pos.y() - s / 2, s, s)
            handle.setPen(pen)
            handle.setBrush(brush)
            handle.setZValue(10000)
            handle.setData(1, handle_type)
            self._scene.addItem(handle)
            self._handles.append(handle)

        # Rotation handle (circle above top center)
        rot_pos = QPointF(bounds.center().x(), bounds.top() - 20)
        rot_handle = QGraphicsEllipseItem(rot_pos.x() - s / 2, rot_pos.y() - s / 2, s, s)
        rot_handle.setPen(pen)
        rot_handle.setBrush(QColor(255, 167, 38, 200))
        rot_handle.setZValue(10000)
        rot_handle.setData(1, HandleType.ROTATION)
        self._scene.addItem(rot_handle)
        self._rotation_handle = rot_handle

    def hide_handles(self):
        """Remove all transform handles from the scene."""
        for handle in self._handles:
            self._scene.removeItem(handle)
        self._handles.clear()

        if self._rotation_handle:
            self._scene.removeItem(self._rotation_handle)
            self._rotation_handle = None

    def handle_at(self, scene_pos: QPointF) -> HandleType | None:
        """Check if a position hits a transform handle."""
        for handle in self._handles:
            if handle.contains(handle.mapFromScene(scene_pos)):
                return handle.data(1)
        if self._rotation_handle and self._rotation_handle.contains(
            self._rotation_handle.mapFromScene(scene_pos)
        ):
            return HandleType.ROTATION
        return None

    # --- Begin/End transform (for undo/redo integration) ---

    def begin_transform(self, items: list[QGraphicsItem]):
        """Capture initial state before a transform operation."""
        self._initial_positions.clear()
        self._initial_transforms.clear()
        for item in items:
            self._initial_positions[item] = QPointF(item.pos())
            self._initial_transforms[item] = QTransform(item.transform())
        self.transform_started.emit()

    def end_transform(self):
        """Signal that the transform is complete (for undo/redo)."""
        self._initial_positions.clear()
        self._initial_transforms.clear()
        self.transform_finished.emit()

    def cancel_transform(self, items: list[QGraphicsItem]):
        """Revert items to their initial state."""
        for item in items:
            if item in self._initial_positions:
                item.setPos(self._initial_positions[item])
            if item in self._initial_transforms:
                item.setTransform(self._initial_transforms[item])
        self._initial_positions.clear()
        self._initial_transforms.clear()

    # --- Helpers ---

    @staticmethod
    def _get_bounds(items: list[QGraphicsItem]) -> QRectF:
        bounds = QRectF()
        for item in items:
            bounds = bounds.united(item.sceneBoundingRect())
        return bounds
