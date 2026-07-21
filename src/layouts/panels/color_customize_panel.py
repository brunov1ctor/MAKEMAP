"""Color Customize Panel ("Personalizar") — full inline color picker (hue
bar, sat/val square, RGB sliders, hex) plus a freehand-paintable pixel grid
where more than one color can be painted in (e.g. thirds of blue/yellow/red
for a "Napolitano" striped look) instead of a single solid fill. Opened
from a ColorField's "Personalizar" button; rides beside the Texto panel,
same riding-panel pattern as RegionEditPanel beside RegionSettingsPanel —
positioned by MainLayout, not through PanelManager's single-slot layout.

The hue/sat/rgb/hex controls pick the current "paintbrush" color; painting
the grid below writes that color into whichever cells are clicked/dragged
over. Reuses the HueBar/SatValSquare/ColorSlider widgets already built for
the Terrain background color picker rather than re-implementing an HSV
picker."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider
from src.engines.typography import PAINT_GRID_COLS, PAINT_GRID_ROWS


class PixelGridPaint(QFrame):
    """Freehand-paintable grid — click/drag writes the current brush color
    into whichever cells the cursor passes over."""

    painted = Signal()  # a cell changed — panel reads .cells

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols, self.rows = PAINT_GRID_COLS, PAINT_GRID_ROWS
        self.cells: list[str] = ["#FFFFFF"] * (self.cols * self.rows)
        self._brush_color = "#FFFFFF"
        self.setFixedHeight(70)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(f"border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;")

    def set_brush_color(self, hex_color: str):
        self._brush_color = hex_color

    def load(self, cells: list[str] | None, fallback_color: str):
        n = self.cols * self.rows
        self.cells = list(cells) if cells and len(cells) == n else [fallback_color] * n
        self.update()

    def clear_to(self, hex_color: str):
        self.cells = [hex_color] * (self.cols * self.rows)
        self.update()
        self.painted.emit()

    def _cell_at(self, pos: QPointF):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return None
        x = int(pos.x() * self.cols / w)
        y = int(pos.y() * self.rows / h)
        if 0 <= x < self.cols and 0 <= y < self.rows:
            return x, y
        return None

    def _paint_at(self, pos: QPointF):
        cell = self._cell_at(pos)
        if cell is None:
            return
        x, y = cell
        idx = y * self.cols + x
        if self.cells[idx] != self._brush_color:
            self.cells[idx] = self._brush_color
            self.update()
            self.painted.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._paint_at(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._paint_at(event.position())

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        cw, ch = w / self.cols, h / self.rows
        for y in range(self.rows):
            for x in range(self.cols):
                rect = QRectF(x * cw, y * ch, cw + 0.6, ch + 0.6)
                p.fillRect(rect, QColor(self.cells[y * self.cols + x]))
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        for x in range(1, self.cols):
            p.drawLine(QPointF(x * cw, 0), QPointF(x * cw, h))
        for y in range(1, self.rows):
            p.drawLine(QPointF(0, y * ch), QPointF(w, y * ch))
        p.end()


class ColorCustomizePanel(QFrame):
    """Single shared instance reused for whichever ColorField opened it —
    same as RegionEditPanel is reused across zone cards."""

    PANEL_WIDTH = 300

    pattern_changed = Signal(list)  # flat list[str] of PAINT_GRID_COLS*PAINT_GRID_ROWS hex cells
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._hsv = [0, 0, 100]  # h(0-359), s(0-100), v(0-100)
        self._color = "#FFFFFF"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(8)

        layout.addLayout(self._build_header())
        layout.addWidget(self._separator())

        self.hue_bar = HueBar()
        self.hue_bar.setFixedHeight(16)
        self.hue_bar.hue_changed.connect(self._on_hue_changed)
        layout.addWidget(self.hue_bar)

        self.sv_square = SatValSquare()
        self.sv_square.setFixedHeight(110)
        self.sv_square.sv_changed.connect(self._on_sv_changed)
        layout.addWidget(self.sv_square)

        self.r_slider = ColorSlider("R", 0, 255, 255)
        self.g_slider = ColorSlider("G", 0, 255, 255)
        self.b_slider = ColorSlider("B", 0, 255, 255)
        for slider in (self.r_slider, self.g_slider, self.b_slider):
            slider.value_changed.connect(self._on_rgb_slider_changed)
            layout.addWidget(slider)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(6)
        self.swatch = QLabel()
        self.swatch.setFixedSize(24, 24)
        hex_row.addWidget(self.swatch)

        hash_label = QLabel("#")
        hash_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hash_label)
        self.hex_input = QLineEdit("FFFFFF")
        self.hex_input.setMaxLength(6)
        self.hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; padding: 3px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self.hex_input.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self.hex_input, 1)
        layout.addLayout(hex_row)
        layout.addWidget(self._separator())

        preview_row = QHBoxLayout()
        preview_row.addWidget(self._section_label("Área de pré-visualização"))
        preview_row.addStretch()
        self.clear_btn = QToolButton()
        self.clear_btn.setText("Limpar")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_SECONDARY}; background: rgba(255,255,255,0.04);
                padding: 2px 6px; font-size: 9px;
            }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        preview_row.addWidget(self.clear_btn)
        layout.addLayout(preview_row)

        self.grid = PixelGridPaint()
        self.grid.painted.connect(self._on_grid_painted)
        layout.addWidget(self.grid)

        self.set_color("#FFFFFF")

    # ─── Header / shared building blocks ───

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(6)

        title = QLabel("Personalizar")
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
        return header

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10pt; background: transparent; border: none;")
        return label

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    # ─── Picker sync (mirrors TerrainBackgroundSection's HSV<->RGB<->hex sync) ───

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self.sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1] = s
        self._hsv[2] = v
        self._apply_hsv()

    def _on_rgb_slider_changed(self, _val: int):
        color = QColor(self.r_slider.value(), self.g_slider.value(), self.b_slider.value())
        h = color.hsvHue() if color.hsvHue() >= 0 else 0
        self._hsv = [h, color.hsvSaturation() * 100 // 255, color.value() * 100 // 255]
        self.hue_bar.blockSignals(True)
        self.hue_bar.set_hue(h)
        self.hue_bar.blockSignals(False)
        self.sv_square.blockSignals(True)
        self.sv_square.set_hue(h)
        self.sv_square.set_sv(self._hsv[1], self._hsv[2])
        self.sv_square.blockSignals(False)
        self._set_brush_color(color.name())

    def _apply_hsv(self):
        color = QColor.fromHsv(self._hsv[0], self._hsv[1] * 255 // 100, self._hsv[2] * 255 // 100)
        self.r_slider.blockSignals(True)
        self.g_slider.blockSignals(True)
        self.b_slider.blockSignals(True)
        self.r_slider.set_value(color.red())
        self.g_slider.set_value(color.green())
        self.b_slider.set_value(color.blue())
        self.r_slider.blockSignals(False)
        self.g_slider.blockSignals(False)
        self.b_slider.blockSignals(False)
        self._set_brush_color(color.name())

    def _on_hex_entered(self):
        text = self.hex_input.text().strip().lstrip("#")
        if len(text) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in text):
            self.set_color(f"#{text}")

    def _set_brush_color(self, hex_color: str):
        """A hue/sv/rgb/hex edit only changes what color painting the grid
        will lay down next — it must NOT repaint the grid itself, same as a
        real paint app's color picker leaves the canvas alone."""
        self._color = hex_color
        self.hex_input.blockSignals(True)
        self.hex_input.setText(hex_color.lstrip("#"))
        self.hex_input.blockSignals(False)
        self.swatch.setStyleSheet(
            f"background: {hex_color}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self.grid.set_brush_color(hex_color)

    def _on_grid_painted(self):
        self.pattern_changed.emit(list(self.grid.cells))

    def _on_clear_clicked(self):
        self.grid.clear_to(self._color)

    # ─── Public API ───

    def set_color(self, hex_color: str):
        """Set the current paintbrush color (hue/sv/rgb/hex mixer) without
        touching the grid — used both for user hex entry and for loading a
        field's representative color when the panel opens."""
        color = QColor(hex_color)
        if not color.isValid():
            return
        h = color.hsvHue() if color.hsvHue() >= 0 else 0
        self._hsv = [h, color.hsvSaturation() * 100 // 255, color.value() * 100 // 255]

        self.hue_bar.blockSignals(True)
        self.hue_bar.set_hue(h)
        self.hue_bar.blockSignals(False)
        self.sv_square.blockSignals(True)
        self.sv_square.set_hue(h)
        self.sv_square.set_sv(self._hsv[1], self._hsv[2])
        self.sv_square.blockSignals(False)
        for slider, value in ((self.r_slider, color.red()), (self.g_slider, color.green()), (self.b_slider, color.blue())):
            slider.blockSignals(True)
            slider.set_value(value)
            slider.blockSignals(False)
        self._set_brush_color(color.name())

    def load_pattern(self, cells: list[str] | None, base_color: str):
        """Load whichever target's existing painted grid (or a uniform
        fallback of base_color if it's never been painted) and set the
        brush to base_color."""
        self.set_color(base_color)
        self.grid.load(cells, base_color)

    def color(self) -> str:
        return self._color

    def paintEvent(self, event):
        paint_glass_panel(self)
