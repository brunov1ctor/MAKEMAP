"""Region Card — compact two-zone card: thumbnail | name/tipo/stats | actions.

Matches the flat-list CRUD mock exactly:
- Left: a ~1/3-width panoramic thumbnail, rounded corners.
- Center: color dot + name (bold) on top, "Tipo: X" below, then a stats
  row with area (km²) and object count.
- Right: eye (visibility) + "..." overflow menu (Renomear, Editar,
  Localizar, Apagar Pintura, Excluir).

Clicking the card body only highlights it (`selected`) — it does NOT open
the edit sub painel; that's "Editar" from the menu now.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QStackedWidget,
    QLineEdit, QMenu, QSizePolicy, QComboBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QPixmap, QPainter, QPainterPath, QDragEnterEvent, QDropEvent

from src.styles.tokens import Colors

_THUMB_W, _THUMB_H = 84, 72


class _RegionThumbLabel(QLabel):
    """RegionCard's thumbnail — accepts a dragged-in image file, or a
    plain click to browse (fallback for no drag-and-drop), same idea as
    the Mobs panel's portrait picker (_DropImageButton) — lets a região
    carry a real reference photo instead of just the flat color swatch.
    Once a photo is set it takes priority over the swatch (see
    RegionCard.set_color) and stays fixed regardless of how the região
    itself is painted — it's a reference image, not a live preview."""

    image_dropped = Signal(str)  # local file path, dropped or picked

    _ACCEPTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._photo_pixmap: QPixmap | None = None

    def has_photo(self) -> bool:
        return self._photo_pixmap is not None

    def set_photo_pixmap(self, pixmap: QPixmap | None):
        self._photo_pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self.update()

    def paintEvent(self, event):
        if self._photo_pixmap is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(path)
        scaled = self._photo_pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()

    def _first_accepted_path(self, mime_data) -> str | None:
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(self._ACCEPTED_SUFFIXES):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and self._first_accepted_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        path = self._first_accepted_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.image_dropped.emit(path)
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path, _selected = QFileDialog.getOpenFileName(
                self, "Selecionar Imagem da Região", "", "Imagens (*.png *.jpg *.jpeg *.webp)",
            )
            if path:
                self.image_dropped.emit(path)
        super().mousePressEvent(event)


class RegionCard(QFrame):
    """A single região (painted zone) entry."""

    selected = Signal(str)
    deleted = Signal(str)
    edit_requested = Signal(str)  # "Editar" — opens the Região Selecionada sub painel
    renamed = Signal(str, str)
    locate_requested = Signal(str)
    visibility_toggled = Signal(str, bool)
    paint_cleared = Signal(str)  # "Apagar Pintura" — clears the mask, keeps the card
    terrain_changed = Signal(str, str)  # region_id, terrain_id ("" = Mapa Infinito)
    image_changed = Signal(str, str)  # region_id, local file path (dropped or picked)
    hover_entered = Signal(str)  # mouse entered the card — glow the matching região on the map
    hover_left = Signal(str)

    def __init__(self, region_id: str, name: str, color: QColor, category_label: str = "",
                 area_m2: float = 0.0, object_count: int = 0, visible: bool = True,
                 terrain_label: str = "Mapa Infinito",
                 terrain_id: str = "", photo: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.region_id = region_id
        self._selected = False
        self._visible = visible
        self._category_label = category_label
        self._area_m2 = area_m2
        self._object_count = object_count
        self._terrain_label = terrain_label
        self._terrain_options: list[tuple[str, str]] = []
        self._terrain_id = terrain_id
        self._color = QColor(color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._build_style(False))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # ─── Left: panoramic thumbnail — a user photo (dropped/picked via
        # _RegionThumbLabel) takes priority over the flat color swatch;
        # never the painted mask's own shape, which would make the
        # thumbnail visibly change on every stroke instead of staying a
        # stable "what this região represents" preview. ───
        self._thumb = _RegionThumbLabel()
        self._thumb.setFixedSize(_THUMB_W, _THUMB_H)
        self._thumb.setScaledContents(True)
        self._thumb.setToolTip("Clique ou arraste uma imagem")
        self._thumb.setStyleSheet(f"""
            background: {color.name()}; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
        """)
        self._thumb.image_dropped.connect(self._on_image_dropped)
        if photo is not None and not photo.isNull():
            self._thumb.set_photo_pixmap(photo)
        layout.addWidget(self._thumb)

        # ─── Center: name / tipo / stats ───
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
        """)
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.editingFinished.connect(self._finish_rename)

        self._name_stack.addWidget(self._name_label)
        self._name_stack.addWidget(self._name_edit)
        self._name_stack.setCurrentIndex(0)
        name_row.addWidget(self._name_stack, 1)
        center_col.addLayout(name_row)

        self._type_label = QLabel()
        self._type_label.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 9px;
            background: transparent; border: none;
        """)
        center_col.addWidget(self._type_label)

        terrain_row = QHBoxLayout()
        terrain_row.setSpacing(4)
        terrain_icon = QLabel("🖌")
        terrain_icon.setStyleSheet("font-size: 9px; background: transparent; border: none;")
        terrain_row.addWidget(terrain_icon)

        self._terrain_combo = QComboBox()
        self._terrain_combo.setFixedHeight(16)
        self._terrain_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._terrain_combo.setStyleSheet(f"""
            QComboBox {{
                color: {Colors.TEXT_MUTED}; font-size: 9px;
                background: transparent; border: none; padding: 0 2px;
            }}
            QComboBox:hover {{ color: {Colors.TEXT_SECONDARY}; }}
            QComboBox::drop-down {{ border: none; width: 10px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; selection-background-color: {Colors.ACCENT_DIM};
                font-size: 10px;
            }}
        """)
        self._terrain_combo.addItem("Mapa Infinito", "")
        self._terrain_combo.currentIndexChanged.connect(self._on_terrain_combo_changed)
        terrain_row.addWidget(self._terrain_combo, 1)
        center_col.addLayout(terrain_row)

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

        self._refresh_meta()

        layout.addLayout(center_col, 1)

        # ─── Right: eye + "..." menu ───
        actions_col = QVBoxLayout()
        actions_col.setSpacing(2)

        self._eye_btn = QToolButton()
        self._eye_btn.setFixedSize(22, 22)
        self._eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setChecked(visible)
        self._eye_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 12px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); }}
        """)
        self._refresh_eye()
        self._eye_btn.clicked.connect(self._on_eye_clicked)
        actions_col.addWidget(self._eye_btn)

        self._menu_btn = QToolButton()
        self._menu_btn.setText("⋯")
        self._menu_btn.setFixedSize(22, 22)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 14px; font-weight: bold;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY}; }}
            QToolButton::menu-indicator {{ image: none; }}
        """)
        menu_style = f"""
            QMenu {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; padding: 4px;
            }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """
        menu = QMenu(self._menu_btn)
        menu.setStyleSheet(menu_style)
        menu.addAction("Renomear", self._start_rename)
        menu.addAction("Editar", lambda: self.edit_requested.emit(self.region_id))
        menu.addAction("Localizar", lambda: self.locate_requested.emit(self.region_id))

        # "Apagar Pintura" opens a submenu with the actual confirm action —
        # keeps the confirmation contained inside the "..." menu itself
        # (hovering it and clicking again is the deliberate two-step),
        # instead of a banner elsewhere in the panel that's disconnected
        # from which card it's about.
        clear_menu = menu.addMenu("Apagar Pintura")
        clear_menu.setStyleSheet(menu_style)
        clear_menu.addAction(
            "Confirmar — apagar toda a pintura", lambda: self.paint_cleared.emit(self.region_id)
        )

        menu.addSeparator()
        menu.addAction("Excluir", lambda: self.deleted.emit(self.region_id))
        self._menu_btn.setMenu(menu)
        actions_col.addWidget(self._menu_btn)
        actions_col.addStretch()

        layout.addLayout(actions_col)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.region_id)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.hover_entered.emit(self.region_id)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_left.emit(self.region_id)
        super().leaveEvent(event)

    def set_selected(self, sel: bool):
        self._selected = sel
        self.setStyleSheet(self._build_style(sel))

    def _build_style(self, sel: bool) -> str:
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
            self.renamed.emit(self.region_id, new_name)
        self._name_stack.setCurrentIndex(0)

    def _on_eye_clicked(self):
        self._visible = self._eye_btn.isChecked()
        self._refresh_eye()
        self.visibility_toggled.emit(self.region_id, self._visible)

    def _refresh_eye(self):
        self._eye_btn.setText("👁" if self._visible else "🚫")
        self._eye_btn.setToolTip("Ocultar" if self._visible else "Mostrar")

    def set_name(self, name: str):
        self._name_label.setText(name)

    def set_category_label(self, label: str):
        self._category_label = label
        self._refresh_meta()

    def set_terrain_label(self, label: str):
        self._terrain_label = label or "Mapa Infinito"
        self._refresh_meta()

    def set_terrain_options(self, options: list[tuple[str, str]]):
        """Populate the "pintando em" dropdown — (terrain_id, name) pairs,
        keeping the current selection if it's still one of the options."""
        current_id = self._terrain_id
        self._terrain_options = options
        self._terrain_combo.blockSignals(True)
        self._terrain_combo.clear()
        self._terrain_combo.addItem("Mapa Infinito", "")
        idx_to_select = 0
        for i, (tid, name) in enumerate(options, start=1):
            self._terrain_combo.addItem(name, tid)
            if tid == current_id:
                idx_to_select = i
        self._terrain_combo.setCurrentIndex(idx_to_select)
        self._terrain_combo.blockSignals(False)

    def set_terrain_id(self, terrain_id: str):
        self._terrain_id = terrain_id or ""
        self._terrain_combo.blockSignals(True)
        idx = self._terrain_combo.findData(self._terrain_id)
        self._terrain_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._terrain_combo.blockSignals(False)

    def _on_terrain_combo_changed(self, index: int):
        terrain_id = self._terrain_combo.itemData(index) or ""
        self._terrain_id = terrain_id
        self.terrain_changed.emit(self.region_id, terrain_id)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._dot.setStyleSheet(f"background: {self._color.name()}; border-radius: 4px;")
        if not self._thumb.has_photo():
            self._thumb.setStyleSheet(f"""
                background: {self._color.name()}; border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.15);
            """)

    def set_photo(self, pixmap: QPixmap | None):
        """The user-uploaded reference photo (dropped/picked on the
        thumbnail, or loaded back from mobs.image_path-equivalent
        painted_zones.image_path) — takes priority over the flat color
        swatch (see set_color)."""
        self._thumb.set_photo_pixmap(pixmap)
        if pixmap is None or pixmap.isNull():
            self.set_color(self._color)

    def _on_image_dropped(self, path: str):
        self.image_changed.emit(self.region_id, path)

    def set_stats(self, area_m2: float, object_count: int):
        self._area_m2 = area_m2
        self._object_count = object_count
        self._refresh_meta()

    def _refresh_meta(self):
        type_text = f"Tipo: {self._category_label}" if self._category_label else ""
        self._type_label.setText(type_text)
        self._type_label.setVisible(bool(type_text))
        area_km2 = self._area_m2 / 1_000_000
        area_text = f"{area_km2:.0f} km²" if area_km2 >= 1 else f"{area_km2:.2f} km²" if area_km2 >= 0.01 else f"{self._area_m2:.0f} m²"
        self._area_label.setText(f"📐 {area_text}")
        self._count_label.setText(f"📦 {self._object_count} objeto{'s' if self._object_count != 1 else ''}")

    @property
    def name(self) -> str:
        return self._name_label.text()

    @property
    def is_visible_state(self) -> bool:
        return self._visible
