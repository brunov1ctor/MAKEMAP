"""Inline Color Picker Widgets — HueBar, SatValSquare, ColorSlider."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QImage

from src.styles.tokens import Colors


class HueBar(QFrame):
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
        for x in range(w):
            hue = int(x * 359 / w)
            p.setPen(QPen(QColor.fromHsv(hue, 255, 255), 1))
            p.drawLine(x, 0, x, h)
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


class SatValSquare(QFrame):
    """Saturation (x) / Value (y) picker square."""
    sv_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self._sat = 100
        self._val = 100
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


class ColorSlider(QFrame):
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
