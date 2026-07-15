"""Asset Adjustments Service — centraliza ajustes visuais (brilho/contraste) dos assets."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QColor, QPixmap


def apply_brightness_contrast(img: QImage, brightness: int, contrast: int) -> QImage:
    """Apply brightness (-100..100) and contrast (-100..100) to a QImage."""
    if img.isNull() or (brightness == 0 and contrast == 0):
        return img
    result = img.copy()
    b = brightness / 100.0
    c = (contrast + 100) / 100.0
    for y in range(result.height()):
        for x in range(result.width()):
            px = result.pixelColor(x, y)
            r = min(255, max(0, int(px.red() * c + b * 255)))
            g = min(255, max(0, int(px.green() * c + b * 255)))
            bl = min(255, max(0, int(px.blue() * c + b * 255)))
            result.setPixelColor(x, y, QColor(r, g, bl, px.alpha()))
    return result


class AssetAdjustmentsService(QObject):
    """Serviço global de ajustes visuais por asset path.

    Signals:
        changed(str, int, int) — emitido quando um ajuste muda (path, brightness, contrast)
    """

    changed = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adjustments: dict[str, tuple[int, int]] = {}

    def set(self, asset_path: str, brightness: int, contrast: int):
        """Define brilho/contraste para um asset. Emite changed."""
        prev = self._adjustments.get(asset_path, (0, 0))
        if prev == (brightness, contrast):
            return
        self._adjustments[asset_path] = (brightness, contrast)
        self.changed.emit(asset_path, brightness, contrast)

    def get(self, asset_path: str) -> tuple[int, int]:
        """Retorna (brightness, contrast) para um asset. (0,0) se sem ajuste."""
        return self._adjustments.get(asset_path, (0, 0))

    def get_adjusted_pixmap(self, asset_path: str, pixmap: QPixmap) -> QPixmap:
        """Retorna o pixmap com ajustes aplicados (ou original se sem ajuste)."""
        b, c = self.get(asset_path)
        if b == 0 and c == 0:
            return pixmap
        img = apply_brightness_contrast(pixmap.toImage(), b, c)
        return QPixmap.fromImage(img)

    def get_adjusted_image(self, asset_path: str) -> QImage:
        """Carrega e retorna QImage ajustada a partir do path."""
        img = QImage(asset_path)
        b, c = self.get(asset_path)
        if b == 0 and c == 0:
            return img
        return apply_brightness_contrast(img, b, c)

    def clear(self, asset_path: str):
        """Remove ajustes de um asset."""
        if asset_path in self._adjustments:
            del self._adjustments[asset_path]
            self.changed.emit(asset_path, 0, 0)

    def clear_all(self):
        """Remove todos os ajustes."""
        paths = list(self._adjustments.keys())
        self._adjustments.clear()
        for p in paths:
            self.changed.emit(p, 0, 0)
