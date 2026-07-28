"""AssetEffectsPanel — paint which regions of an asset DEFINITION (not a
placed instance) get a special visual effect (see src/engines/
asset_effects.py). Opened from a card's "✨" button (see AssetRowCard /
AssetEffectsMediator). A single shared instance, floating INSIDE the app
(same "no window outside the app" rule as every other picker here — see
ColorField/ColorCustomizePanel) — reused for whichever asset's card
triggers it, positioned by MainLayout, not a QDialog.

The paintable grid (EffectGridPaint) mirrors PixelGridPaint's click/drag
mechanic (src/layouts/panels/color_customize_panel.py) — same interaction,
but each cell stores an effect key instead of a color."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.engines.asset_effects import ASSET_EFFECT_TYPES, EFFECT_GRID_SIZE, empty_cells

_PREVIEW_COLORS = {
    "emissivo": QColor(255, 220, 150, 170),
    "aura": QColor(150, 200, 255, 170),
    "glitter": QColor(255, 255, 255, 170),
    "fumaca": QColor(150, 130, 170, 170),
    "distorcao": QColor(180, 220, 255, 170),
}


class EffectGridPaint(QFrame):
    painted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = self.rows = EFFECT_GRID_SIZE
        self.cells: list[str] = empty_cells()
        self._brush = "emissivo"
        self._thumbnail: QPixmap | None = None
        self.setFixedSize(280, 280)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet(f"border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;")

    def set_brush(self, key: str):
        self._brush = key

    def set_thumbnail(self, thumbnail: QPixmap | None):
        self._thumbnail = thumbnail
        self.update()

    def load(self, cells: list[str]):
        n = self.cols * self.rows
        self.cells = list(cells) if cells and len(cells) == n else empty_cells()
        self.update()

    def clear_all(self):
        self.cells = empty_cells()
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
        if self.cells[idx] != self._brush:
            self.cells[idx] = self._brush
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
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self._thumbnail is not None and not self._thumbnail.isNull():
            scaled = self._thumbnail.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            p.fillRect(0, 0, w, h, QColor(20, 24, 32))
            p.drawPixmap(x, y, scaled)
        else:
            p.fillRect(0, 0, w, h, QColor(30, 34, 44))

        cw, ch = w / self.cols, h / self.rows
        for y in range(self.rows):
            for x in range(self.cols):
                key = self.cells[y * self.cols + x]
                if not key:
                    continue
                color = _PREVIEW_COLORS.get(key, QColor(255, 255, 255, 120))
                p.fillRect(QRectF(x * cw, y * ch, cw + 0.6, ch + 0.6), color)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        for x in range(1, self.cols):
            p.drawLine(QPointF(x * cw, 0), QPointF(x * cw, h))
        for y in range(1, self.rows):
            p.drawLine(QPointF(0, y * ch), QPointF(w, y * ch))
        p.end()


class AssetEffectsPanel(QFrame):
    PANEL_WIDTH = 320

    saved = Signal(str, list)  # asset_id, cells
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asset_id = ""
        # Fixed size rather than PanelManager._content_height()'s dynamic
        # sizeHint() lookup — this panel's layout never actually changes
        # shape (load_asset() only swaps text/pixmap/cells, same widgets
        # every time), and sizeHint() on a widget that hasn't been laid out
        # yet reads as 0 right after the very first show(), leaving every
        # button with zero clickable area until some later resize happens
        # to fix it up.
        self.setFixedSize(self.PANEL_WIDTH, 470)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._title = QLabel("✨ Efeitos do Asset")
        self._title.setWordWrap(True)
        self._title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        header.addWidget(self._title, 1)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        hint = QLabel("Pinte as regiões que devem ter o efeito escolhido — cada carimbo desse asset no mapa vai mostrar o efeito nessas posições.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10pt; background: transparent; border: none;")
        layout.addWidget(hint)

        self.grid = EffectGridPaint()
        grid_row = QHBoxLayout()
        grid_row.addStretch()
        grid_row.addWidget(self.grid)
        grid_row.addStretch()
        layout.addLayout(grid_row)

        palette_row = QHBoxLayout()
        palette_row.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, icon, label in ASSET_EFFECT_TYPES:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setChecked(key == "emissivo")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(34, 34)
            btn.setStyleSheet(f"""
                QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px;
                    background: rgba(255,255,255,0.04); font-size: 15px; }}
                QToolButton:hover {{ border-color: {Colors.BORDER_HOVER}; }}
                QToolButton:checked {{ border-color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            """)
            btn.clicked.connect(lambda _=False, k=key: self.grid.set_brush(k))
            self._group.addButton(btn)
            palette_row.addWidget(btn)
        erase_btn = QToolButton()
        erase_btn.setText("⌫")
        erase_btn.setToolTip("Borracha (Nenhum)")
        erase_btn.setCheckable(True)
        erase_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        erase_btn.setFixedSize(34, 34)
        erase_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px;
                background: rgba(255,255,255,0.04); font-size: 15px; color: {Colors.TEXT_SECONDARY}; }}
            QToolButton:hover {{ border-color: {Colors.BORDER_HOVER}; }}
            QToolButton:checked {{ border-color: {Colors.WARNING}; background: rgba(255,167,38,0.15); }}
        """)
        erase_btn.clicked.connect(lambda: self.grid.set_brush(""))
        self._group.addButton(erase_btn)
        palette_row.addWidget(erase_btn)
        palette_row.addStretch()
        layout.addLayout(palette_row)

        btn_row = QHBoxLayout()
        clear_btn = QToolButton()
        clear_btn.setText("Limpar tudo")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_SECONDARY}; background: rgba(255,255,255,0.04); padding: 5px 10px; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        clear_btn.clicked.connect(self.grid.clear_all)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()

        close2_btn = QToolButton()
        close2_btn.setText("Fechar")
        close2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close2_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_SECONDARY}; background: rgba(255,255,255,0.04); padding: 5px 12px; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        close2_btn.clicked.connect(self.close_requested.emit)
        btn_row.addWidget(close2_btn)

        save_btn = QToolButton()
        save_btn.setText("Salvar")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.ACCENT}; border-radius: 4px;
                color: {Colors.TEXT_PRIMARY}; background: {Colors.ACCENT_DIM}; padding: 5px 12px; font-size: 10px; font-weight: bold; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.28); }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def load_asset(self, asset_id: str, asset_name: str, thumbnail: QPixmap | None, cells: list[str]):
        self.asset_id = asset_id
        self._title.setText(f"✨ Efeitos — {asset_name or asset_id}")
        self.grid.set_thumbnail(thumbnail)
        self.grid.load(cells)

    def _on_save(self):
        self.saved.emit(self.asset_id, list(self.grid.cells))

    def paintEvent(self, event):
        paint_glass_panel(self)
