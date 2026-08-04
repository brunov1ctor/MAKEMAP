"""SpawnMobSubPanel — mobs within the currently picked category.

Rides next to SpawnPanel the same adjacent-panel pattern AssetBrowserPanel
uses beside BrushToolPanel: opened when a category row is clicked, lists
every mob tagged under it (including subfolders), closes itself once one
is picked.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QScrollArea,
    QWidget, QToolButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QPainter, QPainterPath

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel

_THUMB = 40


class _MobRow(QFrame):
    """One mob entry: rounded portrait thumbnail + name, click to pick."""

    clicked = Signal(str)

    def __init__(self, mob_id: str, name: str, pixmap: QPixmap | None, fallback_icon: str, parent=None):
        super().__init__(parent)
        self.mob_id = mob_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QFrame:hover {{ background: rgba(255,255,255,0.09); border-color: {Colors.ACCENT}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(_THUMB, _THUMB)
        if pixmap and not pixmap.isNull():
            thumb.setPixmap(self._rounded(pixmap))
        else:
            thumb.setText(fallback_icon)
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet("background: rgba(255,255,255,0.06); border-radius: 6px; font-size: 18px;")
        lay.addWidget(thumb)

        name_lbl = QLabel(name)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(name_lbl, 1)

    @staticmethod
    def _rounded(pixmap: QPixmap) -> QPixmap:
        # Contain-fit onto a plate, not a cover-fit crop — mob portraits are
        # almost always already a tightly-cropped character on a
        # transparent background, so cropping to fill the square just
        # zoomed in and sliced off whatever stuck out (ears/horns/wings).
        # See portrait_compose._circular_portrait for the same reasoning.
        out = QPixmap(_THUMB, _THUMB)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(0, 0, _THUMB, _THUMB, 6, 6)
        p.setClipPath(path)
        p.fillRect(0, 0, _THUMB, _THUMB, QColor(255, 255, 255, 10))
        inset = round(_THUMB * 0.9)
        scaled = pixmap.scaled(
            inset, inset, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (_THUMB - scaled.width()) // 2
        y = (_THUMB - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)
        p.end()
        return out

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.mob_id)
        super().mousePressEvent(event)


class SpawnMobSubPanel(QFrame):
    """Adjacent sub-panel listing every mob in the currently picked category."""

    PANEL_WIDTH = 240

    mob_selected = Signal(str)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 8)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._title = QLabel("MOBS")
        self._title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(self._title, 1)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    def set_category(self, label: str, icon: str, mobs: list[tuple[str, str, QPixmap | None]]):
        """`mobs` = [(mob_id, name, portrait_pixmap_or_None), ...]"""
        self._title.setText(f"{icon} {label}".upper())
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not mobs:
            empty = QLabel("Nenhum mob nesta categoria.")
            empty.setWordWrap(True)
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
            self._list_layout.insertWidget(0, empty)
            return
        for mob_id, name, pixmap in mobs:
            row = _MobRow(mob_id, name, pixmap, icon)
            row.clicked.connect(self.mob_selected.emit)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)

    def paintEvent(self, event):
        paint_glass_panel(self)
