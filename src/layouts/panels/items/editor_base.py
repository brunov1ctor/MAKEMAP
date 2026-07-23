"""Shared building blocks for the two center editors (EDITOR DE ITEM and
EDITOR DE HABILIDADE): the pill tab-bar, the iOS-style toggle switch, the
"Alterar Ícone" thumbnail button and a couple of small layout helpers.

Kept separate from either editor so the two stay visually identical where
they overlap (header shape, tab bar, toggles) without copy-paste.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QAbstractButton,
    QFrame, QSizePolicy, QStackedWidget, QButtonGroup, QGridLayout,
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, Property, QRectF
from PySide6.QtGui import QPainter, QColor, QPixmap

from src.styles.tokens import Colors


class ToggleSwitch(QAbstractButton):
    """A small rounded on/off switch (blue when on) — matches the toggles in
    the reference's Propriedades/Mecânica tabs. Checkable; emits toggled()
    like any checkable button, with a short slide animation on the knob."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 20)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(120)
        self.toggled.connect(self._on_toggled)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float):
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _on_toggled(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(38, 20)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        radius = h / 2
        # Track
        on = QColor(Colors.ACCENT)
        off = QColor(255, 255, 255, 40)
        track = QColor(on) if self.isChecked() else off
        if self.isChecked():
            track.setAlpha(200)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)
        # Knob
        knob_d = h - 6
        x = 3 + self._offset * (w - knob_d - 6)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 3, knob_d, knob_d))
        p.end()


class EditorTabBar(QWidget):
    """A row of pill tabs that drives a QStackedWidget. Emits tab_changed
    with the new index; the owning editor builds one page per tab."""

    tab_changed = Signal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, label in enumerate(labels):
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(i == 0)
            btn.setStyleSheet(f"""
                QToolButton {{ background: transparent; color: {Colors.TEXT_MUTED};
                    border: none; border-bottom: 2px solid transparent;
                    padding: 5px 10px; font-size: 10px; font-weight: bold; }}
                QToolButton:hover {{ color: {Colors.TEXT_SECONDARY}; }}
                QToolButton:checked {{ color: {Colors.ACCENT}; border-bottom: 2px solid {Colors.ACCENT}; }}
            """)
            btn.clicked.connect(lambda _=False, idx=i: self.tab_changed.emit(idx))
            self._group.addButton(btn, i)
            row.addWidget(btn)
        row.addStretch()

    def set_current(self, index: int):
        btn = self._group.button(index)
        if btn:
            btn.setChecked(True)


class IconButton(QToolButton):
    """The square item/skill icon thumbnail with an emoji fallback. Clicking
    it (wired by the editor) browses for an image; a pixmap is shown once set.
    Also accepts an image file dropped straight from Explorer/Finder — emits
    image_dropped with the local path (same idea as the Mobs portrait's
    _DropImageButton)."""

    image_dropped = Signal(str)
    _ACCEPTED = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

    def __init__(self, fallback: str = "📦", parent=None, size: tuple[int, int] = (72, 72)):
        super().__init__(parent)
        self._fallback = fallback
        self._size = size
        self.setFixedSize(*size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self._base_style()
        self.set_image("")

    def _base_style(self, drop: bool = False):
        border = Colors.ACCENT if drop else Colors.BORDER_SUBTLE
        bg = "rgba(79,195,247,0.15)" if drop else "rgba(255,255,255,0.05)"
        self.setStyleSheet(f"""
            QToolButton {{ background: {bg}; border: 1px solid {border};
                border-radius: 10px; font-size: 30px; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)

    def _accepted_path(self, mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(self._ACCEPTED):
                return path
        return None

    def dragEnterEvent(self, event):
        if self._accepted_path(event.mimeData()):
            self._base_style(drop=True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._base_style(drop=False)

    def dropEvent(self, event):
        path = self._accepted_path(event.mimeData())
        self._base_style(drop=False)
        if path:
            event.acceptProposedAction()
            self.set_image(path)
            self.image_dropped.emit(path)
        else:
            event.ignore()

    def set_image(self, path: str):
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            self.setIcon(QPixmap())
            self.setText(self._fallback)
            return
        # Margem de 12px reservada pra borda/padding do botão, igual ao
        # 72->60 original. Ao contrário do quadrado, um tamanho retangular
        # (o cabeçalho dos editores de Dungeons usa 150x84) precisa de um
        # crop manual — QIcon::pixmap() reencolhe mantendo proporção ao
        # desenhar, então só passar KeepAspectRatioByExpanding sem cortar
        # deixaria a imagem "encolhida de volta" e sobrando espaço vazio.
        w, h = self._size[0] - 12, self._size[1] - 12
        scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
        x = max(0, (scaled.width() - w) // 2)
        y = max(0, (scaled.height() - h) // 2)
        cropped = scaled.copy(x, y, w, h)
        self.setIcon(cropped)
        self.setIconSize(QSize(w, h))
        self.setText("")


def editor_frame(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """A center-column glass card with the small-caps accent title row.
    Returns (frame, content_layout, title_row) so the caller can drop
    header widgets (an ID label, an Importar button) into the title row."""
    from src.layouts.panels.items.constants import panel_frame_style, sub_header
    frame = QFrame()
    frame.setObjectName("subpanel")
    frame.setStyleSheet(panel_frame_style())
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(12, 10, 12, 12)
    outer.setSpacing(8)
    title_row = QHBoxLayout()
    title_row.setSpacing(8)
    title_row.addWidget(sub_header(title))
    title_row.addStretch()
    outer.addLayout(title_row)
    return frame, outer, title_row


def toggle_row(label: str, switch: ToggleSwitch) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(6)
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
    row.addWidget(lbl)
    row.addStretch()
    row.addWidget(switch)
    return row
