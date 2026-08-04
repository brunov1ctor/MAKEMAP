"""ImageDropThumb — small rounded-corner thumbnail that accepts a dragged-in
image file, or a plain click to browse (fallback for no drag-and-drop).

Shared by every edit sub painel that lets an entry carry a reference photo
(Região, Terreno, ...) — extracted so the picker itself (and its "Nenhuma
Imagem Selecionada" caption) lives in one place instead of being
copy-pasted per panel.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QFileDialog
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QDragEnterEvent, QDropEvent

_ACCEPTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class ImageDropThumb(QLabel):
    image_dropped = Signal(str)  # local file path, dropped or picked

    def __init__(self, dialog_title: str = "Selecionar Imagem", parent=None):
        super().__init__(parent)
        self._dialog_title = dialog_title
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
            if path and path.lower().endswith(_ACCEPTED_SUFFIXES):
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
                self, self._dialog_title, "", "Imagens (*.png *.jpg *.jpeg *.webp)",
            )
            if path:
                self.image_dropped.emit(path)
        super().mousePressEvent(event)
