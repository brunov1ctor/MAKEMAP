"""Terrain Card — compact two-zone card: thumbnail | name/stats | actions.

Mirrors RegionCard's layout (see region/region_card.py) now that Terrain
gets the same flat-list CRUD treatment: a reference photo (or flat color
swatch) on the left, name + área/objetos stats in the middle, and a
locate + "..." overflow menu (Renomear, Editar, Localizar, Excluir) on the
right. Drag-to-reorder (grabbing the card's own border) is unchanged from
the old thin-row version.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QStackedWidget,
    QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QPoint, QMimeData, QRectF
from PySide6.QtGui import QColor, QDrag, QPixmap, QPainter, QPainterPath

from src.styles.tokens import Colors
from src.layouts.panels.card_widgets import overflow_menu_button

_THUMB_W, _THUMB_H = 84, 72


class TerrainCard(QFrame):
    """A single terreno entry card with thumbnail, stats, and actions."""

    selected = Signal(str)
    deleted = Signal(str)
    delete_requested = Signal(str)  # pede confirmação antes de excluir
    edit_requested = Signal(str)  # "Editar" — opens the Terreno sub painel
    renamed = Signal(str, str)
    locate_requested = Signal(str)

    DRAG_MARGIN = 8

    def __init__(self, terrain_id: str, name: str, color: QColor,
                 area_m2: float = 0.0, object_count: int = 0,
                 photo: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.terrain_id = terrain_id
        self._selected = False
        self._color = QColor(color)
        self._area_m2 = area_m2
        self._object_count = object_count
        self._drag_start_pos: QPoint | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setStyleSheet(self._build_style(False))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # ─── Left: thumbnail — a user photo takes priority over the flat
        # color swatch, same rule as RegionCard. ───
        self._thumb = QLabel()
        self._thumb.setFixedSize(_THUMB_W, _THUMB_H)
        self._thumb.setScaledContents(True)
        self._thumb.setStyleSheet(f"""
            background: {color.name()}; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
        """)
        self._photo_pixmap: QPixmap | None = None
        if photo is not None and not photo.isNull():
            self._set_photo_pixmap(photo)
        layout.addWidget(self._thumb)

        # ─── Center: name + stats ───
        center_col = QVBoxLayout()
        center_col.setSpacing(3)
        center_col.setContentsMargins(0, 2, 0, 2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        self._dot = QLabel()
        self._dot.setFixedSize(9, 9)
        self._dot.setStyleSheet(f"background: {color.name()}; border-radius: 4px;")
        name_row.addWidget(self._dot)

        self._name_stack = QStackedWidget()
        self._name_stack.setFixedHeight(18)
        self._name_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")

        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;
            background: transparent; border: none;
        """)

        self._name_edit = QLineEdit(name)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;
                background: transparent; border: none; padding: 0;
            }}
            QLineEdit:focus {{ background: transparent; border: none; }}
        """)
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.editingFinished.connect(self._finish_rename)

        self._name_stack.addWidget(self._name_label)
        self._name_stack.addWidget(self._name_edit)
        self._name_stack.setCurrentIndex(0)
        name_row.addWidget(self._name_stack, 1)
        center_col.addLayout(name_row)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._area_label = QLabel()
        self._area_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 9px;
            background: transparent; border: none;
        """)
        self._count_label = QLabel()
        self._count_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 9px;
            background: transparent; border: none;
        """)
        stats_row.addWidget(self._area_label)
        stats_row.addWidget(self._count_label)
        stats_row.addStretch()
        center_col.addLayout(stats_row)
        center_col.addStretch()

        self._refresh_stats()

        layout.addLayout(center_col, 1)

        # ─── Right: locate + "..." menu ───
        actions_col = QVBoxLayout()
        actions_col.setSpacing(2)

        self._locate_btn = QToolButton()
        self._locate_btn.setText("📍")
        self._locate_btn.setFixedSize(22, 22)
        self._locate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._locate_btn.setToolTip("Localizar no mapa")
        self._locate_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 12px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.ACCENT}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        self._locate_btn.clicked.connect(lambda: self.locate_requested.emit(self.terrain_id))
        actions_col.addWidget(self._locate_btn)

        self._menu_btn, menu = overflow_menu_button()
        menu.addAction("Renomear", self._start_rename)
        menu.addAction("Editar", lambda: self.edit_requested.emit(self.terrain_id))
        menu.addAction("Localizar", lambda: self.locate_requested.emit(self.terrain_id))
        menu.addSeparator()
        menu.addAction("Excluir", lambda: self.delete_requested.emit(self.terrain_id))
        actions_col.addWidget(self._menu_btn)
        actions_col.addStretch()

        layout.addLayout(actions_col)

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
                    border-radius: 10px;
                }}
            """
        if sel:
            return f"""
                QFrame {{
                    background: rgba(79,195,247,0.12); border: 1.5px solid {Colors.ACCENT};
                    border-radius: 10px;
                }}
            """
        return f"""
            QFrame {{
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 10px;
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

    def set_name(self, name: str):
        self._name_label.setText(name)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._dot.setStyleSheet(f"background: {self._color.name()}; border-radius: 4px;")
        if self._photo_pixmap is None:
            self._thumb.setStyleSheet(f"""
                background: {self._color.name()}; border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.15);
            """)

    def _set_photo_pixmap(self, pixmap: QPixmap):
        rounded = QPixmap(_THUMB_W, _THUMB_H)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, _THUMB_W, _THUMB_H), 8, 8)
        painter.setClipPath(path)
        scaled = pixmap.scaled(
            _THUMB_W, _THUMB_H, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
        )
        x = (_THUMB_W - scaled.width()) // 2
        y = (_THUMB_H - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()
        self._photo_pixmap = pixmap
        self._thumb.setStyleSheet("background: transparent; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px;")
        self._thumb.setPixmap(rounded)

    def set_photo(self, pixmap: QPixmap | None):
        if pixmap is not None and not pixmap.isNull():
            self._set_photo_pixmap(pixmap)
        else:
            self._photo_pixmap = None
            self._thumb.setPixmap(QPixmap())
            self.set_color(self._color)

    def set_stats(self, area_m2: float, object_count: int):
        self._area_m2 = area_m2
        self._object_count = object_count
        self._refresh_stats()

    def _refresh_stats(self):
        area_km2 = self._area_m2 / 1_000_000
        area_text = f"{area_km2:.0f} km²" if area_km2 >= 1 else f"{area_km2:.2f} km²" if area_km2 >= 0.01 else f"{self._area_m2:.0f} m²"
        self._area_label.setText(f"📐 {area_text}")
        self._count_label.setText(f"📦 {self._object_count} objeto{'s' if self._object_count != 1 else ''}")

    @property
    def name(self) -> str:
        return self._name_label.text()

    @property
    def is_visible(self) -> bool:
        return True
