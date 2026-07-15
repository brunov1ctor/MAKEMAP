"""Terrain Settings Panel — map boundary configuration + terrain CRUD + background."""

from __future__ import annotations

import os
import uuid

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QCheckBox, QToolButton, QWidget, QButtonGroup, QScrollArea,
    QLineEdit, QFileDialog, QStackedWidget, QGridLayout, QTabBar,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPoint, QMimeData, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush, QDrag, QPixmap, QIcon, QImage

from src.styles.tokens import Colors
from src.layouts.panels.brush_panel import BrushSlider, FlowLayout


# ─── Terrain Card ────────────────────────────────────────────────────────────

class TerrainCard(QFrame):
    """A single terrain entry card with name, visibility toggle, and delete."""

    toggled = Signal(str, bool)      # id, visible
    deleted = Signal(str)            # id
    selected = Signal(str)           # id
    renamed = Signal(str, str)       # id, new_name
    drag_started = Signal(str)       # id

    DRAG_MARGIN = 8  # pixels from edge to trigger drag

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

        self._name_stack.addWidget(self._name_label)   # index 0
        self._name_stack.addWidget(self._name_edit)    # index 1
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
            # Find parent panel and reorder
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


# ─── Inline Color Picker Widgets ─────────────────────────────────────────────

class _HueBar(QFrame):
    """Horizontal hue spectrum bar (0-359)."""
    hue_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet("border: 1px solid rgba(255,255,255,0.15); border-radius: 3px;")

    def set_hue(self, hue: int):
        self._hue = max(0, min(359, hue))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Draw hue gradient
        for x in range(w):
            hue = int(x * 359 / w)
            p.setPen(QPen(QColor.fromHsv(hue, 255, 255), 1))
            p.drawLine(x, 0, x, h)
        # Draw indicator
        ix = int(self._hue * w / 359)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawRect(ix - 2, 0, 4, h - 1)
        p.end()

    def mousePressEvent(self, event):
        self._update_hue(event.pos().x())

    def mouseMoveEvent(self, event):
        self._update_hue(event.pos().x())

    def _update_hue(self, x: int):
        hue = max(0, min(359, int(x * 359 / self.width())))
        self._hue = hue
        self.update()
        self.hue_changed.emit(hue)


class _SatValSquare(QFrame):
    """Saturation (x) / Value (y) picker square."""
    sv_changed = Signal(int, int)  # sat 0-100, val 0-100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self._sat = 100  # 0-100
        self._val = 100  # 0-100
        self._cache: QPixmap | None = None
        self._cache_hue = -1
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet("border: 1px solid rgba(255,255,255,0.15); border-radius: 3px;")

    def set_hue(self, hue: int):
        self._hue = hue
        self._cache = None
        self.update()

    def set_sv(self, s: int, v: int):
        self._sat = s
        self._val = v
        self.update()

    def _build_cache(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        img = QImage(w, h, QImage.Format.Format_RGB32)
        for y in range(h):
            v = 255 - int(y * 255 / h)
            for x in range(w):
                s = int(x * 255 / w)
                img.setPixelColor(x, y, QColor.fromHsv(self._hue, s, v))
        self._cache = QPixmap.fromImage(img)
        self._cache_hue = self._hue

    def paintEvent(self, event):
        p = QPainter(self)
        if self._cache is None or self._cache_hue != self._hue:
            self._build_cache()
        if self._cache:
            p.drawPixmap(0, 0, self._cache)
        # Draw crosshair
        w, h = self.width(), self.height()
        cx = int(self._sat * w / 100)
        cy = int((100 - self._val) * h / 100)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.drawEllipse(cx - 5, cy - 5, 10, 10)
        p.end()

    def mousePressEvent(self, event):
        self._update_sv(event.pos())

    def mouseMoveEvent(self, event):
        self._update_sv(event.pos())

    def _update_sv(self, pos: QPoint):
        w, h = self.width(), self.height()
        s = max(0, min(100, int(pos.x() * 100 / w)))
        v = max(0, min(100, 100 - int(pos.y() * 100 / h)))
        self._sat = s
        self._val = v
        self.update()
        self.sv_changed.emit(s, v)


class _ColorSlider(QFrame):
    """Single RGB channel slider with label and value."""
    value_changed = Signal(int)

    def __init__(self, label: str, min_val: int, max_val: int, default: int, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedHeight(20)
        self._min = min_val
        self._max = max_val

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setFixedWidth(12)
        lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(lbl)

        from PySide6.QtWidgets import QSlider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(min_val, max_val)
        self._slider.setValue(default)
        self._slider.setFixedHeight(14)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.wheelEvent = lambda e: e.ignore()
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {Colors.BORDER_SUBTLE}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 10px; height: 10px; margin: -3px 0; background: {Colors.ACCENT}; border-radius: 5px; }}
            QSlider::sub-page:horizontal {{ background: {Colors.ACCENT_DIM}; border-radius: 2px; }}
        """)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider, 1)

        self._val_label = QLabel(str(default))
        self._val_label.setFixedWidth(24)
        self._val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._val_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9px; background: transparent; border: none;")
        layout.addWidget(self._val_label)

    def _on_change(self, val: int):
        self._val_label.setText(str(val))
        self.value_changed.emit(val)

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, val: int):
        self._slider.setValue(val)
        self._val_label.setText(str(val))

    def blockSignals(self, block: bool):
        self._slider.blockSignals(block)


# ─── Main Panel ──────────────────────────────────────────────────────────────

class TerrainSettingsPanel(QFrame):
    """Side panel for map terrain/boundary configuration."""

    PANEL_WIDTH = 300

    # Signals
    dimensions_changed = Signal(int, int)
    shape_changed = Signal(str)
    infinite_toggled = Signal(bool)
    close_requested = Signal()
    terrain_added = Signal(str, str)        # id, name
    terrain_removed = Signal(str)           # id
    terrain_selected = Signal(str)          # id
    terrain_renamed = Signal(str, str)      # id, new_name
    terrain_visibility = Signal(str, bool)  # id, visible
    background_changed = Signal(str, str)   # type ("color"/"image"/"gif"/"none"), value

    # Default colors for new terrains (cycles)
    _PALETTE = [
        QColor(34, 139, 34), QColor(210, 180, 100), QColor(30, 100, 180),
        QColor(128, 128, 128), QColor(101, 67, 33), QColor(207, 16, 32),
        QColor(240, 248, 255), QColor(80, 80, 80), QColor(139, 90, 43),
        QColor(26, 166, 154),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                width: 4px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)

        icon = QLabel("🗺")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)

        title = QLabel("Terrain")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        layout.addWidget(self._sep())

        # ─── Infinite toggle (estilo filtros rápidos) ───
        self._infinite_widget = QFrame()
        self._infinite_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._infinite_widget.setStyleSheet("background: transparent; border: none;")
        inf_layout = QHBoxLayout(self._infinite_widget)
        inf_layout.setContentsMargins(4, 2, 8, 2)
        inf_layout.setSpacing(6)

        self._inf_box = QLabel("✓")
        self._inf_box.setFixedSize(16, 16)
        self._inf_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inf_checked = True
        self._update_inf_style()
        inf_layout.addWidget(self._inf_box)

        inf_label = QLabel("Mapa Infinito")
        inf_label.setStyleSheet(f"""
            font-size: 11px; color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        inf_layout.addWidget(inf_label)
        inf_layout.addStretch()

        self._infinite_widget.mousePressEvent = self._on_inf_click
        layout.addWidget(self._infinite_widget)

        self._sep1 = self._sep()
        layout.addWidget(self._sep1)
        self._sep1.hide()

        # ─── Dimensions + Shape (hidden when infinite) ───
        self._bounds_widget = QWidget()
        self._bounds_widget.setStyleSheet("background: transparent; border: none;")
        bounds_layout = QVBoxLayout(self._bounds_widget)
        bounds_layout.setContentsMargins(0, 0, 0, 0)
        bounds_layout.setSpacing(6)

        dims_label = QLabel("Dimensões")
        dims_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        bounds_layout.addWidget(dims_label)

        self.width_slider = BrushSlider("Largura", "↔", 512, 16384, 4096, "px")
        self.height_slider = BrushSlider("Altura", "↕", 512, 16384, 4096, "px")
        bounds_layout.addWidget(self.width_slider)
        bounds_layout.addWidget(self.height_slider)

        self.width_slider.value_changed.connect(self._on_dims_changed)
        self.height_slider.value_changed.connect(self._on_dims_changed)

        bounds_layout.addWidget(self._sep())

        shape_label = QLabel("Forma do Limite")
        shape_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        bounds_layout.addWidget(shape_label)

        shape_row1 = QHBoxLayout()
        shape_row1.setSpacing(6)
        shape_row2 = QHBoxLayout()
        shape_row2.setSpacing(6)

        self._shape_group = QButtonGroup(self)
        self._shape_group.setExclusive(True)

        shapes_row1 = [
            ("▭", "rectangle", "Retângulo"),
            ("□", "square", "Quadrado"),
            ("○", "circle", "Círculo"),
            ("⬡", "hexagon", "Hexágono"),
        ]
        shapes_row2 = [
            ("△", "triangle", "Triângulo"),
            ("⬬", "ellipse", "Elipse"),
            ("⬠", "pentagon", "Pentágono"),
            ("✏", "freehand", "Forma Livre"),
        ]

        self._shape_buttons: dict[str, QToolButton] = {}

        for icon_text, shape_id, tooltip in shapes_row1:
            btn = self._make_shape_btn(icon_text, shape_id, tooltip)
            shape_row1.addWidget(btn)
        shape_row1.addStretch()

        for icon_text, shape_id, tooltip in shapes_row2:
            btn = self._make_shape_btn(icon_text, shape_id, tooltip)
            shape_row2.addWidget(btn)
        shape_row2.addStretch()

        bounds_layout.addLayout(shape_row1)
        bounds_layout.addLayout(shape_row2)

        self._shape_buttons["rectangle"].setChecked(True)
        self._current_shape = "rectangle"

        layout.addWidget(self._bounds_widget)
        # Start hidden (infinite mode is default)
        self._bounds_widget.hide()

        self._sep2 = self._sep()
        layout.addWidget(self._sep2)
        self._sep2.hide()

        # ─── Terrain CRUD ───
        self._crud_widget = QWidget()
        self._crud_widget.setStyleSheet("background: transparent; border: none;")
        crud_layout = QVBoxLayout(self._crud_widget)
        crud_layout.setContentsMargins(0, 0, 0, 0)
        crud_layout.setSpacing(6)

        crud_header = QHBoxLayout()
        crud_header.setSpacing(6)

        crud_label = QLabel("Terrenos")
        crud_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        crud_header.addWidget(crud_label)
        crud_header.addStretch()

        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setFixedSize(22, 22)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                font-size: 14px; font-weight: bold;
                color: {Colors.ACCENT}; background: rgba(79,195,247,0.08);
            }}
            QToolButton:hover {{ background: rgba(79,195,247,0.2); }}
        """)
        add_btn.clicked.connect(self._on_add_terrain)
        crud_header.addWidget(add_btn)

        crud_layout.addLayout(crud_header)

        # Name input (for adding)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Nome do terreno...")
        self._name_input.setFixedHeight(26)
        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._name_input.returnPressed.connect(self._on_add_terrain)
        crud_layout.addWidget(self._name_input)

        # Scrollable card list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(160)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                width: 4px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.2); border-radius: 2px;
            }}
        """)

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        crud_layout.addWidget(self._scroll)

        layout.addWidget(self._crud_widget)
        # Start hidden (infinite mode is default)
        self._crud_widget.hide()

        self._sep3 = self._sep()
        layout.addWidget(self._sep3)
        self._sep3.hide()

        # ─── Background Customization ───
        bg_header = QHBoxLayout()
        bg_header.setSpacing(6)

        bg_label = QLabel("Plano de Fundo")
        bg_label.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        bg_header.addWidget(bg_label)
        bg_header.addStretch()
        layout.addLayout(bg_header)

        # Background toggle buttons (exclusive toggle)
        bg_row = QHBoxLayout()
        bg_row.setSpacing(6)

        self._bg_buttons: dict[str, QToolButton] = {}
        self._bg_active: str = ""  # "color", "image", "gif" or ""

        for key, icon_text, tooltip in [
            ("color", "🎨", "Cor fixa"),
            ("image", "🖼", "Imagem estática"),
            ("gif", "🎞", "GIF animado"),
        ]:
            btn = QToolButton()
            btn.setText(icon_text)
            btn.setToolTip(tooltip)
            btn.setFixedSize(48, 32)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._bg_btn_style())
            btn.clicked.connect(lambda checked, k=key: self._on_bg_toggle(k))
            bg_row.addWidget(btn)
            self._bg_buttons[key] = btn

        bg_row.addStretch()
        layout.addLayout(bg_row)

        # Inline color picker (shown when color is active)
        self._bg_color_widget = QFrame()
        self._bg_color_widget.setStyleSheet("background: transparent; border: none;")
        color_lay = QVBoxLayout(self._bg_color_widget)
        color_lay.setContentsMargins(0, 4, 0, 4)
        color_lay.setSpacing(6)

        # ── Color spectrum (Hue gradient bar) ──
        self._hue_bar = _HueBar()
        self._hue_bar.setFixedHeight(16)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        color_lay.addWidget(self._hue_bar)

        # ── Saturation/Value square ──
        self._sv_square = _SatValSquare()
        self._sv_square.setFixedHeight(100)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        color_lay.addWidget(self._sv_square)

        # ── RGB Sliders ──
        self._r_slider = _ColorSlider("R", 0, 255, 7)
        self._g_slider = _ColorSlider("G", 0, 255, 17)
        self._b_slider = _ColorSlider("B", 0, 255, 31)
        self._r_slider.value_changed.connect(self._on_rgb_slider_changed)
        self._g_slider.value_changed.connect(self._on_rgb_slider_changed)
        self._b_slider.value_changed.connect(self._on_rgb_slider_changed)
        color_lay.addWidget(self._r_slider)
        color_lay.addWidget(self._g_slider)
        color_lay.addWidget(self._b_slider)

        # ── Hex + Preview row ──
        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hex_label = QLabel("#")
        hex_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hex_label)
        self._hex_input = QLineEdit("07111F")
        self._hex_input.setFixedHeight(22)
        self._hex_input.setMaxLength(6)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; padding: 0 4px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self._hex_input)

        self._bg_color_swatch = QLabel()
        self._bg_color_swatch.setFixedSize(22, 22)
        self._bg_color_swatch.setStyleSheet("background: #07111F; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);")
        hex_row.addWidget(self._bg_color_swatch)
        hex_row.addStretch()
        color_lay.addLayout(hex_row)

        # ── Basic colors palette ──
        basic_label = QLabel("Cores básicas")
        basic_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        color_lay.addWidget(basic_label)

        palette_grid = QGridLayout()
        palette_grid.setSpacing(3)
        self._color_palette = [
            "#000000", "#434343", "#666666", "#999999", "#b7b7b7", "#cccccc", "#d9d9d9", "#efefef", "#f3f3f3", "#ffffff",
            "#980000", "#ff0000", "#ff9900", "#ffff00", "#00ff00", "#00ffff", "#4a86e8", "#0000ff", "#9900ff", "#ff00ff",
            "#e6b8af", "#f4cccc", "#fce5cd", "#fff2cc", "#d9ead3", "#d0e0e3", "#c9daf8", "#cfe2f3", "#d9d2e9", "#ead1dc",
            "#dd7e6b", "#ea9999", "#f9cb9c", "#ffe599", "#b6d7a8", "#a2c4c9", "#a4c2f4", "#9fc5e8", "#b4a7d6", "#d5a6bd",
            "#cc4125", "#e06666", "#f6b26b", "#ffd966", "#93c47d", "#76a5af", "#6d9eeb", "#6fa8dc", "#8e7cc3", "#c27ba0",
        ]
        self._bg_selected_color = "#07111F"
        self._palette_swatches: list[QLabel] = []
        for i, c in enumerate(self._color_palette):
            swatch = QLabel()
            swatch.setFixedSize(18, 18)
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            swatch.setStyleSheet(f"background: {c}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.15);")
            swatch.mousePressEvent = lambda e, color=c: self._select_bg_color(color)
            palette_grid.addWidget(swatch, i // 10, i % 10)
            self._palette_swatches.append(swatch)
        color_lay.addLayout(palette_grid)

        # ── Custom colors row ──
        custom_label = QLabel("Cores personalizadas")
        custom_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        color_lay.addWidget(custom_label)

        self._custom_colors_layout = QHBoxLayout()
        self._custom_colors_layout.setSpacing(3)
        self._custom_color_slots: list[QLabel] = []
        for i in range(10):
            slot = QLabel()
            slot.setFixedSize(18, 18)
            slot.setCursor(Qt.CursorShape.PointingHandCursor)
            slot.setStyleSheet(f"background: rgba(255,255,255,0.06); border-radius: 3px; border: 1px dashed {Colors.BORDER_SUBTLE};")
            slot.mousePressEvent = lambda e, idx=i: self._on_custom_slot_click(idx)
            self._custom_colors_layout.addWidget(slot)
            self._custom_color_slots.append(slot)
        self._custom_colors_layout.addStretch()
        color_lay.addLayout(self._custom_colors_layout)

        # Add to custom button
        add_custom_btn = QToolButton()
        add_custom_btn.setText("+ Adicionar às personalizadas")
        add_custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_custom_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; font-size: 9px; color: {Colors.ACCENT};
                background: transparent; padding: 2px;
            }}
            QToolButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        add_custom_btn.clicked.connect(self._add_to_custom_colors)
        color_lay.addWidget(add_custom_btn)

        self._bg_color_widget.hide()
        self._custom_color_data: list[str] = [""] * 10
        self._hsv = [0, 100, 100]  # current H, S, V
        layout.addWidget(self._bg_color_widget)

        # Inline asset browser (shown when image/gif is active)
        self._bg_file_widget = QFrame()
        self._bg_file_widget.setStyleSheet("background: transparent; border: none;")
        file_lay = QVBoxLayout(self._bg_file_widget)
        file_lay.setContentsMargins(0, 4, 0, 4)
        file_lay.setSpacing(4)

        # Tabs for categories
        self._bg_tabs = QTabBar()
        self._bg_tabs.setExpanding(False)
        self._bg_tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: transparent; color: {Colors.TEXT_SECONDARY};
                padding: 3px 6px; font-size: 9px; border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {Colors.ACCENT}; border-bottom-color: {Colors.ACCENT};
            }}
            QTabBar::tab:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._bg_tabs.wheelEvent = lambda e: e.ignore()
        self._bg_categories = ["space", "terrain", "mystics", "nature", "abstract"]
        for cat in self._bg_categories:
            self._bg_tabs.addTab(cat.capitalize())
        self._bg_tabs.addTab("📁 Meu PC")
        self._bg_tabs.currentChanged.connect(self._on_bg_tab_changed)
        file_lay.addWidget(self._bg_tabs)

        # Asset grid scroll
        self._bg_grid_scroll = QScrollArea()
        self._bg_grid_scroll.setWidgetResizable(True)
        self._bg_grid_scroll.setFixedHeight(140)
        self._bg_grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._bg_grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._bg_grid_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._bg_grid_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                width: 3px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.TEXT_MUTED}; border-radius: 1px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._bg_grid_container = QWidget()
        self._bg_grid_container.setStyleSheet("background: transparent;")
        self._bg_grid_layout = FlowLayout(self._bg_grid_container, spacing=4)
        self._bg_grid_layout.setContentsMargins(4, 4, 4, 4)
        self._bg_grid_scroll.setWidget(self._bg_grid_container)
        file_lay.addWidget(self._bg_grid_scroll)

        # Selected file label
        self._bg_file_label = QLabel("Nenhum selecionado")
        self._bg_file_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        file_lay.addWidget(self._bg_file_label)

        self._bg_file_widget.hide()
        self._bg_asset_buttons: list[QToolButton] = []
        layout.addWidget(self._bg_file_widget)
        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

        # State
        self._cards: dict[str, TerrainCard] = {}
        self._selected_id: str = ""
        self._color_idx = 0
        self._bg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "library", "backgrounds")

    def _update_inf_style(self):
        if self._inf_checked:
            self._inf_box.setStyleSheet(f"""
                background: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
                border-radius: 3px; color: #ffffff; font-size: 10px; font-weight: bold;
            """)
            self._inf_box.setText("✓")
        else:
            self._inf_box.setStyleSheet(f"""
                background: transparent; border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 3px; color: transparent; font-size: 10px;
            """)
            self._inf_box.setText("")

    def _on_inf_click(self, event):
        self._inf_checked = not self._inf_checked
        self._update_inf_style()
        self._on_infinite_toggled(self._inf_checked)

    # ─── Shape helpers ───

    def _make_shape_btn(self, icon_text: str, shape_id: str, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(icon_text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(48, 32)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;
                font-size: 16px; color: {Colors.TEXT_SECONDARY};
                background: rgba(255,255,255,0.04);
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY};
            }}
            QToolButton:checked {{
                background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
        """)
        btn.clicked.connect(lambda checked, s=shape_id: self._on_shape_selected(s))
        self._shape_group.addButton(btn)
        self._shape_buttons[shape_id] = btn
        return btn

    def _sep(self):
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _bg_btn_style(self) -> str:
        return f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;
                font-size: 16px; color: {Colors.TEXT_SECONDARY};
                background: rgba(255,255,255,0.04);
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY};
            }}
            QToolButton:checked {{
                background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
        """

    # ─── Background ───

    def _on_bg_toggle(self, key: str):
        """Toggle background type. Click again to deactivate."""
        btn = self._bg_buttons[key]
        if self._bg_active == key:
            # Deactivate
            btn.setChecked(False)
            self._bg_active = ""
            self._bg_color_widget.hide()
            self._bg_file_widget.hide()
            self.background_changed.emit("none", "")
        else:
            # Activate this, deactivate others
            for k, b in self._bg_buttons.items():
                b.setChecked(k == key)
            self._bg_active = key
            if key == "color":
                self._bg_color_widget.show()
                self._bg_file_widget.hide()
            elif key in ("image", "gif"):
                self._bg_color_widget.hide()
                self._bg_file_widget.show()
                # Load first category
                self._bg_tabs.setCurrentIndex(0)
                self._load_bg_assets(self._bg_categories[0])
        # Notify parent to resize panel
        if self.parent() and hasattr(self.parent(), '_reposition'):
            self.parent()._reposition()

    def _select_bg_color(self, color: str):
        self._bg_selected_color = color
        self._bg_color_swatch.setStyleSheet(
            f"background: {color}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self._hex_input.setText(color.lstrip("#"))
        # Update HSV state and widgets from this color
        qc = QColor(color)
        self._hsv = [qc.hsvHue() if qc.hsvHue() >= 0 else 0, qc.hsvSaturation() * 100 // 255, qc.value() * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._r_slider.set_value(qc.red())
        self._g_slider.set_value(qc.green())
        self._b_slider.set_value(qc.blue())
        self.background_changed.emit("color", color)
        self.close_requested.emit()

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1] = s
        self._hsv[2] = v
        self._apply_hsv()

    def _on_rgb_slider_changed(self, _val: int):
        r = self._r_slider.value()
        g = self._g_slider.value()
        b = self._b_slider.value()
        color = QColor(r, g, b)
        hex_str = color.name()
        self._bg_selected_color = hex_str
        self._bg_color_swatch.setStyleSheet(
            f"background: {hex_str}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self._hex_input.setText(hex_str.lstrip("#"))
        # Update HSV without triggering loop
        h = color.hsvHue() if color.hsvHue() >= 0 else 0
        self._hsv = [h, color.hsvSaturation() * 100 // 255, color.value() * 100 // 255]
        self._hue_bar.blockSignals(True)
        self._hue_bar.set_hue(h)
        self._hue_bar.blockSignals(False)
        self._sv_square.blockSignals(True)
        self._sv_square.set_hue(h)
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sv_square.blockSignals(False)
        self.background_changed.emit("color", hex_str)

    def _apply_hsv(self):
        color = QColor.fromHsv(self._hsv[0], self._hsv[1] * 255 // 100, self._hsv[2] * 255 // 100)
        hex_str = color.name()
        self._bg_selected_color = hex_str
        self._bg_color_swatch.setStyleSheet(
            f"background: {hex_str}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self._hex_input.setText(hex_str.lstrip("#"))
        self._r_slider.blockSignals(True)
        self._g_slider.blockSignals(True)
        self._b_slider.blockSignals(True)
        self._r_slider.set_value(color.red())
        self._g_slider.set_value(color.green())
        self._b_slider.set_value(color.blue())
        self._r_slider.blockSignals(False)
        self._g_slider.blockSignals(False)
        self._b_slider.blockSignals(False)
        self.background_changed.emit("color", hex_str)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in text):
            self._select_bg_color(f"#{text}")

    def _add_to_custom_colors(self):
        """Save current color to the first empty custom slot."""
        for i, c in enumerate(self._custom_color_data):
            if not c:
                self._custom_color_data[i] = self._bg_selected_color
                self._custom_color_slots[i].setStyleSheet(
                    f"background: {self._bg_selected_color}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2);"
                )
                return
        # All full, overwrite first
        self._custom_color_data[0] = self._bg_selected_color
        self._custom_color_slots[0].setStyleSheet(
            f"background: {self._bg_selected_color}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2);"
        )

    def _on_custom_slot_click(self, idx: int):
        if self._custom_color_data[idx]:
            self._select_bg_color(self._custom_color_data[idx])

    def _on_bg_tab_changed(self, index: int):
        """Load assets for the selected background category or open file picker."""
        if index >= len(self._bg_categories):
            # "Meu PC" tab — open file dialog
            self._pick_bg_from_pc()
            return
        category = self._bg_categories[index]
        self._load_bg_assets(category)

    def _load_bg_assets(self, category: str):
        """Scan library/backgrounds/<category> and populate the grid."""
        # Clear existing
        for btn in self._bg_asset_buttons:
            btn.deleteLater()
        self._bg_asset_buttons.clear()

        cat_dir = os.path.join(self._bg_dir, category)
        if not os.path.isdir(cat_dir):
            os.makedirs(cat_dir, exist_ok=True)
            return

        extensions = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")
        files = sorted(f for f in os.listdir(cat_dir)
                       if f.lower().endswith(extensions))

        for fname in files:
            fpath = os.path.join(cat_dir, fname)
            btn = QToolButton()
            btn.setFixedSize(52, 58)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(fname)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(36, 36))
            btn.setText(fname[:7])
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: 2px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                    background: rgba(255,255,255,0.04); padding: 2px;
                    font-size: 8px; color: {Colors.TEXT_MUTED};
                }}
                QToolButton:hover {{ border-color: {Colors.TEXT_SECONDARY}; }}
                QToolButton:checked {{
                    border-color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM};
                }}
            """)
            # Load thumbnail
            pix = QPixmap(fpath)
            if not pix.isNull():
                scaled = pix.scaled(QSize(36, 36), Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
                btn.setIcon(QIcon(scaled))
            btn.clicked.connect(lambda checked, p=fpath, b=btn: self._on_bg_asset_clicked(p, b))
            self._bg_grid_layout.addWidget(btn)
            self._bg_asset_buttons.append(btn)

    def _on_bg_asset_clicked(self, path: str, clicked_btn: QToolButton):
        """Select a background asset from the grid."""
        for btn in self._bg_asset_buttons:
            if btn is not clicked_btn:
                btn.setChecked(False)
        self._bg_file_label.setText(os.path.basename(path))
        bg_type = "gif" if path.lower().endswith(".gif") else "image"
        self.background_changed.emit(bg_type, path)
        self.close_requested.emit()

    def _pick_bg_from_pc(self):
        """Open file dialog only when user explicitly chooses 'Meu PC' tab."""
        if self._bg_active == "gif":
            path, _ = QFileDialog.getOpenFileName(
                self, "Selecionar GIF Animado", "", "GIFs (*.gif)"
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Selecionar Imagem de Fundo", "",
                "Imagens (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
            )
        if path:
            self._bg_file_label.setText(os.path.basename(path))
            bg_type = "gif" if path.lower().endswith(".gif") else "image"
            self.background_changed.emit(bg_type, path)
            self.close_requested.emit()

    # ─── CRUD ───

    def _on_add_terrain(self):
        name = self._name_input.text().strip()
        if not name:
            name = f"Terreno {len(self._cards) + 1}"
        terrain_id = str(uuid.uuid4())
        color = self._PALETTE[self._color_idx % len(self._PALETTE)]
        self._color_idx += 1

        self._add_card(terrain_id, name, color)
        self._name_input.clear()
        self.terrain_added.emit(terrain_id, name)

    def _add_card(self, terrain_id: str, name: str, color: QColor):
        card = TerrainCard(terrain_id, name, color)
        card.selected.connect(self._on_card_selected)
        card.deleted.connect(self._on_card_deleted)
        card.toggled.connect(self._on_card_toggled)
        card.renamed.connect(self._on_card_renamed)

        # Insert before the stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._cards[terrain_id] = card

    def _on_card_selected(self, terrain_id: str):
        self._selected_id = terrain_id
        for tid, card in self._cards.items():
            card.set_selected(tid == terrain_id)
        self.terrain_selected.emit(terrain_id)

    def _on_card_deleted(self, terrain_id: str):
        card = self._cards.pop(terrain_id, None)
        if card:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        if self._selected_id == terrain_id:
            self._selected_id = ""
        self.terrain_removed.emit(terrain_id)

    def _on_card_toggled(self, terrain_id: str, visible: bool):
        self.terrain_visibility.emit(terrain_id, visible)

    def _on_card_renamed(self, terrain_id: str, new_name: str):
        self.terrain_renamed.emit(terrain_id, new_name)

    def _reorder_card(self, source_id: str, target_id: str):
        """Move source card to the position of target card."""
        source_card = self._cards.get(source_id)
        target_card = self._cards.get(target_id)
        if not source_card or not target_card:
            return
        # Remove source from layout
        self._list_layout.removeWidget(source_card)
        # Find target index
        target_idx = self._list_layout.indexOf(target_card)
        # Insert source before target
        self._list_layout.insertWidget(target_idx, source_card)

    # ─── Public API ───

    def add_terrain(self, terrain_id: str, name: str, color: QColor = None):
        """Programmatically add a terrain card."""
        if terrain_id in self._cards:
            return
        c = color or self._PALETTE[self._color_idx % len(self._PALETTE)]
        self._color_idx += 1
        self._add_card(terrain_id, name, c)

    def remove_terrain(self, terrain_id: str):
        """Programmatically remove a terrain card."""
        self._on_card_deleted(terrain_id)

    @property
    def selected_terrain_id(self) -> str:
        return self._selected_id

    # ─── Signals handlers ───

    def _on_infinite_toggled(self, checked: bool):
        show = not checked
        self._bounds_widget.setVisible(show)
        self._crud_widget.setVisible(show)
        self._sep1.setVisible(show)
        self._sep2.setVisible(show)
        self._sep3.setVisible(show)
        self.infinite_toggled.emit(checked)

    def _on_dims_changed(self, _value):
        w = int(self.width_slider.value)
        h = int(self.height_slider.value)
        if self._current_shape == "square":
            sender = self.sender()
            if sender == self.width_slider._slider:
                self.height_slider.set_value(w)
                h = w
            else:
                self.width_slider.set_value(h)
                w = h
        elif self._current_shape == "circle":
            sender = self.sender()
            if sender == self.width_slider._slider:
                self.height_slider.set_value(w)
                h = w
            else:
                self.width_slider.set_value(h)
                w = h
        self.dimensions_changed.emit(w, h)

    def _on_shape_selected(self, shape: str):
        self._current_shape = shape
        if shape in ("square", "circle"):
            val = int(self.width_slider.value)
            self.height_slider.set_value(val)
        self.shape_changed.emit(shape)

    # ─── Properties ───

    @property
    def is_infinite(self) -> bool:
        return self._inf_checked

    @property
    def map_width(self) -> int:
        return int(self.width_slider.value)

    @property
    def map_height(self) -> int:
        return int(self.height_slider.value)

    @property
    def map_shape(self) -> str:
        return self._current_shape

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.fillPath(path, QColor(11, 25, 41, 235))
        grad = QLinearGradient(0, 0, 0, h * 0.15)
        grad.setColorAt(0.0, QColor(255, 255, 255, 10))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawPath(path)
        p.end()
