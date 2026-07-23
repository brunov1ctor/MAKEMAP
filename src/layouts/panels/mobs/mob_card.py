"""MobCard — grid tile for a single mob (thumbnail, name, level, rarity badge).

Clicking a card both selects it (highlight) and loads it into the
MobEditPanel on the right — unlike Região's flat list, there's no separate
"Editar" step here since the detail panel is always visible alongside the
grid.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QMenu, QSizePolicy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import category_icon, rarity_color, rarity_label


class _CoverImageLabel(QLabel):
    """A QLabel that always fills its own current size with the mob's
    image, cropped instead of letterboxed (cover-fit, like CSS
    background-size: cover) — a pixmap pre-scaled once in set_data() stayed
    a small fixed square that didn't match the label's real (layout-
    dependent) size, leaving it floating with empty space around it
    instead of filling the whole thumbnail area. Falls back to plain text
    (the category emoji) when no image is set, via the normal QLabel paint
    path."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._cover_pixmap: QPixmap | None = None

    def set_cover_pixmap(self, pixmap: QPixmap | None):
        self._cover_pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self.update()

    def paintEvent(self, event):
        if self._cover_pixmap is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scaled = self._cover_pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


def _set_icon_or_image(label: _CoverImageLabel, image_path: str, icon: str):
    """Shared by MobCard/MobListRow: shows the mob's own uploaded image,
    filling the whole thumbnail area, if it has one — falling back to the
    category emoji icon otherwise. Previously neither card ever looked at
    image_path at all, so an uploaded portrait only ever showed up in the
    edit panel."""
    pixmap = QPixmap(image_path) if image_path else QPixmap()
    if not pixmap.isNull():
        label.setText("")
        label.set_cover_pixmap(pixmap)
    else:
        label.set_cover_pixmap(None)
        label.setText(icon)

CARD_W = 148
THUMB_H = 96


class MobCard(QFrame):
    """A single mob entry in the grid."""

    selected = Signal(str)
    favorite_toggled = Signal(str, bool)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, mob_id: str, parent=None):
        super().__init__(parent)
        self.mob_id = mob_id
        self._selected = False
        self._favorite = False
        self.setFixedWidth(CARD_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ─── Thumbnail ───
        self._thumb = QFrame()
        self._thumb.setFixedHeight(THUMB_H)
        self._thumb.setStyleSheet("border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);")
        thumb_lay = QVBoxLayout(self._thumb)
        thumb_lay.setContentsMargins(6, 4, 6, 4)

        top_row = QHBoxLayout()
        self._element_badge = QLabel("")
        self._element_badge.setStyleSheet(
            "background: rgba(0,0,0,0.35); border-radius: 8px; padding: 1px 5px; "
            f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; border: none;"
        )
        top_row.addWidget(self._element_badge)
        top_row.addStretch()

        self._fav_btn = QToolButton()
        self._fav_btn.setFixedSize(18, 18)
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; font-size: 13px; color: gold; }"
        )
        self._fav_btn.clicked.connect(self._on_fav_clicked)
        top_row.addWidget(self._fav_btn)
        thumb_lay.addLayout(top_row)

        self._icon_label = _CoverImageLabel("👹")
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet("font-size: 32px; background: transparent; border: none;")
        thumb_lay.addWidget(self._icon_label, 1)
        layout.addWidget(self._thumb)

        # ─── Name ───
        self._name_label = QLabel("")
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._name_label.setFixedHeight(30)
        layout.addWidget(self._name_label)

        # ─── Level + rarity chip ───
        meta_row = QHBoxLayout()
        meta_row.setSpacing(4)
        self._level_label = QLabel("")
        self._level_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;"
        )
        meta_row.addWidget(self._level_label)
        meta_row.addStretch()
        self._rarity_chip = QLabel("")
        self._rarity_chip.setStyleSheet(
            "font-size: 9px; font-weight: bold; border-radius: 6px; padding: 1px 6px;"
        )
        meta_row.addWidget(self._rarity_chip)
        layout.addLayout(meta_row)

        # ─── Category / região ───
        self._sub_label = QLabel("")
        self._sub_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;"
        )
        self._sub_label.setWordWrap(True)
        layout.addWidget(self._sub_label)

        self._refresh_style()

    # ─── Public API ───

    def set_data(self, name: str, level: int, category: str, rarity: str,
                 element: str, zone_label: str, favorite: bool, image_path: str = ""):
        self._name_label.setText(name)
        self._level_label.setText(f"Nv. {level}")
        _set_icon_or_image(self._icon_label, image_path, category_icon(category))
        self._element_badge.setText(element or "—")
        self._sub_label.setText(zone_label or "Sem região")
        self._favorite = favorite
        self._fav_btn.setText("★" if favorite else "☆")

        color = rarity_color(rarity)
        self._rarity_chip.setText(rarity_label(rarity))
        self._rarity_chip.setStyleSheet(
            f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 1px 6px; "
            f"background: {color}33; color: {color};"
        )
        self._thumb.setStyleSheet(
            f"border-radius: 8px; border: 1px solid {color}88; "
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {color}22, stop:1 rgba(0,0,0,0.25));"
        )

    def set_selected(self, sel: bool):
        self._selected = sel
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(79,195,247,0.12); border: 1.5px solid {Colors.ACCENT}; border-radius: 10px; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 10px; }}
                QFrame:hover {{ background: rgba(255,255,255,0.08); }}
            """)

    def _on_fav_clicked(self):
        self._favorite = not self._favorite
        self._fav_btn.setText("★" if self._favorite else "☆")
        self.favorite_toggled.emit(self.mob_id, self._favorite)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.mob_id)
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                         border: 1px solid {Colors.BORDER}; padding: 4px; }}
                QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
                QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
            """)
            menu.addAction("⧉ Duplicar", lambda: self.duplicate_requested.emit(self.mob_id))
            menu.addSeparator()
            menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self.mob_id))
            menu.exec(event.globalPosition().toPoint())
        super().mousePressEvent(event)


class MobListRow(QFrame):
    """Full-width horizontal row for the "Lista" view — same signals as
    MobCard, just a compact single-line layout instead of a grid tile."""

    selected = Signal(str)
    favorite_toggled = Signal(str, bool)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, mob_id: str, parent=None):
        super().__init__(parent)
        self.mob_id = mob_id
        self._selected = False
        self._favorite = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)

        self._fav_btn = QToolButton()
        self._fav_btn.setFixedSize(18, 18)
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.setStyleSheet("QToolButton { border: none; background: transparent; font-size: 13px; color: gold; }")
        self._fav_btn.clicked.connect(self._on_fav_clicked)
        layout.addWidget(self._fav_btn)

        self._icon_label = _CoverImageLabel("👹")
        self._icon_label.setFixedSize(22, 22)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        layout.addWidget(self._icon_label)

        self._name_label = QLabel("")
        self._name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        # Sem word-wrap, o minimumSizeHint de um QLabel é o texto inteiro —
        # numa linha estreita isso empurra o menu_btn (⋯, com Excluir) para
        # fora da área visível em vez de ceder espaço. Ignored faz o rótulo
        # abrir mão do próprio texto na disputa por espaço; só corta
        # visualmente (sem "…"), mas o menu nunca mais some.
        self._name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name_label, 2)

        self._level_label = QLabel("")
        self._level_label.setFixedWidth(50)
        self._level_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(self._level_label)

        self._rarity_chip = QLabel("")
        self._rarity_chip.setFixedWidth(64)
        self._rarity_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rarity_chip.setStyleSheet("font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 0;")
        layout.addWidget(self._rarity_chip)

        self._element_label = QLabel("")
        self._element_label.setFixedWidth(60)
        self._element_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        layout.addWidget(self._element_label)

        self._sub_label = QLabel("")
        self._sub_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        self._sub_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._sub_label, 1)

        menu_btn = QToolButton()
        menu_btn.setText("⋯")
        menu_btn.setFixedSize(20, 20)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 13px; font-weight: bold;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY}; }}
            QToolButton::menu-indicator {{ image: none; }}
        """)
        menu = QMenu(menu_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                     border: 1px solid {Colors.BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("⧉ Duplicar", lambda: self.duplicate_requested.emit(self.mob_id))
        menu.addSeparator()
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self.mob_id))
        menu_btn.setMenu(menu)
        layout.addWidget(menu_btn)

        self._refresh_style()

    def set_data(self, name: str, level: int, category: str, rarity: str,
                 element: str, zone_label: str, favorite: bool, image_path: str = ""):
        self._name_label.setText(name)
        self._level_label.setText(f"Nv. {level}")
        _set_icon_or_image(self._icon_label, image_path, category_icon(category))
        self._element_label.setText(element or "—")
        self._sub_label.setText(zone_label or "Sem região")
        self._favorite = favorite
        self._fav_btn.setText("★" if favorite else "☆")
        color = rarity_color(rarity)
        self._rarity_chip.setText(rarity_label(rarity))
        self._rarity_chip.setStyleSheet(
            f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 0; "
            f"background: {color}33; color: {color};"
        )

    def set_selected(self, sel: bool):
        self._selected = sel
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(79,195,247,0.12); border: 1.5px solid {Colors.ACCENT}; border-radius: 8px; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
                QFrame:hover {{ background: rgba(255,255,255,0.07); }}
            """)

    def _on_fav_clicked(self):
        self._favorite = not self._favorite
        self._fav_btn.setText("★" if self._favorite else "☆")
        self.favorite_toggled.emit(self.mob_id, self._favorite)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.mob_id)
        super().mousePressEvent(event)
