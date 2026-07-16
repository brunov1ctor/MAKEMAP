"""Terrain Card — single terrain entry with name, visibility, drag/drop, and delete."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QStackedWidget, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QPoint, QMimeData
from PySide6.QtGui import QColor, QDrag

from src.styles.tokens import Colors


class TerrainCard(QFrame):
    """A single terrain entry card with name, visibility toggle, and delete."""

    toggled = Signal(str, bool)
    deleted = Signal(str)
    selected = Signal(str)
    renamed = Signal(str, str)
    drag_started = Signal(str)

    DRAG_MARGIN = 8

    def __init__(self, terrain_id: str, name: str, color: QColor, parent=None):
        super().__init__(parent)
        self.terrain_id = terrain_id
        self._selected = False
        self._drag_start_pos: QPoint | None = None
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self._base_style = self._build_style(False)
        self.setStyleSheet(self._base_style)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Color swatch
        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"""
            background: {color.name()}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2);
        """)
        layout.addWidget(swatch)

        # Name (label + edit stacked)
        self._name_stack = QStackedWidget()
        self._name_stack.setFixedHeight(22)

        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 11px;
            background: transparent; border: none;
        """)

        self._name_edit = QLineEdit(name)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT};
                border-radius: 3px; padding: 0 4px;
            }}
        """)
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.editingFinished.connect(self._finish_rename)

        self._name_stack.addWidget(self._name_label)
        self._name_stack.addWidget(self._name_edit)
        self._name_stack.setCurrentIndex(0)
        layout.addWidget(self._name_stack, 1)

        # Locate button
        self._vis_btn = QToolButton()
        self._vis_btn.setText("📍")
        self._vis_btn.setFixedSize(22, 22)
        self._vis_btn.setToolTip("Localizar no mapa")
        self._vis_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vis_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.ACCENT}; }}
        """)
        self._vis_btn.clicked.connect(lambda: self.toggled.emit(self.terrain_id, True))
        layout.addWidget(self._vis_btn)

        # Rename button
        rename_btn = QToolButton()
        rename_btn.setText("✎")
        rename_btn.setFixedSize(22, 22)
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 12px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY}; }}
        """)
        rename_btn.clicked.connect(self._start_rename)
        layout.addWidget(rename_btn)

        # Delete button
        del_btn = QToolButton()
        del_btn.setText("🗑")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}
        """)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.terrain_id))
        layout.addWidget(del_btn)

    def _is_on_border(self, pos: QPoint) -> bool:
        m = self.DRAG_MARGIN
        return (pos.x() < m or pos.x() > self.width() - m or
                pos.y() < m or pos.y() > self.height() - m)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_on_border(event.pos()):
                self._drag_start_pos = event.pos()
            else:
                self._drag_start_pos = None
                self.selected.emit(self.terrain_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None and
                (event.pos() - self._drag_start_pos).manhattanLength() > 10):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.terrain_id)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text() != self.terrain_id:
            event.acceptProposedAction()
            self.setStyleSheet(self._build_style(self._selected, drop_target=True))

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._build_style(self._selected))

    def dropEvent(self, event):
        source_id = event.mimeData().text()
        if source_id and source_id != self.terrain_id:
            event.acceptProposedAction()
            from src.layouts.panels.terrain.panel import TerrainSettingsPanel
            panel = self.parent()
            while panel and not isinstance(panel, TerrainSettingsPanel):
                panel = panel.parent()
            if panel:
                panel._reorder_card(source_id, self.terrain_id)
        self.setStyleSheet(self._build_style(self._selected))

    def set_selected(self, sel: bool):
        self._selected = sel
        self.setStyleSheet(self._build_style(sel))

    def _build_style(self, sel: bool, drop_target: bool = False) -> str:
        if drop_target:
            return f"""
                QFrame {{
                    background: rgba(79,195,247,0.1); border: 2px dashed {Colors.ACCENT};
                    border-radius: 6px;
                }}
            """
        if sel:
            return f"""
                QFrame {{
                    background: {Colors.ACCENT_DIM}; border: 1px solid {Colors.ACCENT};
                    border-radius: 6px;
                }}
            """
        return f"""
            QFrame {{
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px;
            }}
            QFrame:hover {{ background: rgba(255,255,255,0.08); }}
        """

    def _start_rename(self):
        self._name_edit.setText(self._name_label.text())
        self._name_stack.setCurrentIndex(1)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _finish_rename(self):
        if self._name_stack.currentIndex() != 1:
            return
        new_name = self._name_edit.text().strip()
        if new_name and new_name != self._name_label.text():
            self._name_label.setText(new_name)
            self.renamed.emit(self.terrain_id, new_name)
        self._name_stack.setCurrentIndex(0)

    @property
    def name(self) -> str:
        return self._name_label.text()

    @property
    def is_visible(self) -> bool:
        return True
