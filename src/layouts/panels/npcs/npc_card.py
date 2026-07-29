"""NPCCard — grid tile for a single mob (thumbnail, name, level, rarity badge).

Clicking a card both selects it (highlight) and loads it into the
NPCEditPanel on the right — unlike Região's flat list, there's no separate
"Editar" step here since the detail panel is always visible alongside the
grid.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QMenu, QSizePolicy, QGridLayout, QWidget
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath

from src.styles.tokens import Colors
from src.layouts.panels.npcs.categories import (
    category_icon, category_label, category_badge_color, category_image_border_color,
    category_tag_text_color,
)


class _CoverImageLabel(QLabel):
    """A QLabel that shows the npc's whole image, scaled to fit its own
    current size without cropping (contain-fit, like CSS background-size:
    contain — letterboxed/centered instead of cover-fit, which was cutting
    off tall/portrait images that didn't match the thumbnail's aspect
    ratio). A pixmap pre-scaled once in set_data() stayed a small fixed
    square that didn't match the label's real (layout-dependent) size,
    leaving it floating with empty space around it — this scales against
    the label's actual current size instead. Falls back to plain text (the
    category emoji) when no image is set, via the normal QLabel paint
    path."""

    def __init__(self, text: str = "", parent=None, radius: int = 0):
        super().__init__(text, parent)
        self._cover_pixmap: QPixmap | None = None
        self._radius = radius

    def set_cover_pixmap(self, pixmap: QPixmap | None):
        self._cover_pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self.update()

    def paintEvent(self, event):
        if self._cover_pixmap is None:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._radius:
            # The label is stacked full-bleed behind the badge row (see
            # NPCCard._thumb), so nothing else clips its corners to match
            # the rounded frame around it — without this the pixmap's
            # square corners poke out past the frame's rounded ones.
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
            painter.setClipPath(path)
        scaled = self._cover_pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


def _set_icon_or_image(label: _CoverImageLabel, image_path: str, icon: str) -> float | None:
    """Shared by NPCCard/NPCListRow: shows the npc's own uploaded image,
    filling the whole thumbnail area, if it has one — falling back to the
    category emoji icon otherwise. Previously neither card ever looked at
    image_path at all, so an uploaded portrait only ever showed up in the
    edit panel. Returns the image's own aspect ratio (width/height), or
    None with no image — NPCCard.set_data uses this to size THIS card's
    thumbnail box to match its own image instead of a fixed height shared
    by every card, which always left a leftover gap for images whose
    proportions didn't happen to match that fixed box exactly."""
    pixmap = QPixmap(image_path) if image_path else QPixmap()
    if not pixmap.isNull():
        label.setText("")
        label.set_cover_pixmap(pixmap)
        return pixmap.width() / pixmap.height()
    label.set_cover_pixmap(None)
    label.setText(icon)
    return None

_ZONE_BADGE_SIZE = 20


def _rounded_zone_thumb(pixmap: QPixmap, size: int = _ZONE_BADGE_SIZE) -> QPixmap:
    """Cover-fit `pixmap` into a small rounded square — the região badge
    is image-only (see NPCCard.set_data), so this needs to read as a tiny
    icon at a glance, not a cropped-oddly rectangle."""
    scaled = pixmap.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 4, 4)
    p.setClipPath(path)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    p.drawPixmap(x, y, scaled)
    p.end()
    return out


CARD_W = 148
# Fallback height when a card has no image (fixed) — cards WITH an image
# size their own thumbnail box per-image instead (see set_data), bounded
# by MIN/MAX_THUMB_H, in a FlowLayout that already tolerates per-item
# height differences (unlike a strict QGridLayout).
THUMB_H = 180
MIN_THUMB_H = 100
MAX_THUMB_H = 260
_CARD_MARGIN = 6  # matches NPCCard's own layout.setContentsMargins below
THUMB_W = CARD_W - 2 * _CARD_MARGIN  # the thumb's REAL rendered width, not CARD_W itself


class NPCCard(QFrame):
    """A single npc entry in the grid."""

    selected = Signal(str)
    favorite_toggled = Signal(str, bool)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, npc_id: str, parent=None):
        super().__init__(parent)
        self.npc_id = npc_id
        self._selected = False
        self._favorite = False
        self._category_border_color = ""  # "" = default frame border (see _refresh_style)
        self.setFixedWidth(CARD_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN, _CARD_MARGIN)
        layout.setSpacing(4)

        # ─── Thumbnail ───
        # The image fills the whole THUMB_H area (full-bleed) instead of
        # being squeezed into the space left under the badge row — the
        # badge/favorite row is stacked on top of it in the same grid
        # cell instead of living above it in a QVBoxLayout, which used to
        # push the image down and leave it covering only part of the tile.
        self._thumb = QFrame()
        self._thumb.setFixedHeight(THUMB_H)
        self._thumb.setStyleSheet("border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);")
        thumb_stack = QGridLayout(self._thumb)
        thumb_stack.setContentsMargins(0, 0, 0, 0)
        thumb_stack.setSpacing(0)

        self._icon_label = _CoverImageLabel("👹", radius=7)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet("font-size: 32px; background: transparent; border: none;")
        thumb_stack.addWidget(self._icon_label, 0, 0)

        overlay = QWidget()
        overlay.setStyleSheet("background: transparent;")
        overlay_lay = QVBoxLayout(overlay)
        overlay_lay.setContentsMargins(6, 4, 6, 4)
        overlay_lay.addLayout(self._build_badge_row())
        overlay_lay.addStretch()
        thumb_stack.addWidget(overlay, 0, 0)
        overlay.raise_()

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
        self._type_label = QLabel("")
        self._type_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;"
        )
        meta_row.addWidget(self._type_label)
        self._rarity_chip = QLabel("")
        self._rarity_chip.setStyleSheet(
            "font-size: 9px; font-weight: bold; border-radius: 6px; padding: 1px 6px;"
        )
        meta_row.addWidget(self._rarity_chip)
        layout.addLayout(meta_row)

        # ─── Região badge — just the região's own image (no name/icon),
        # a small rounded square. Falls back to plain muted "Sem região"
        # text only when the npc has no região tagged at all. Wrapped in
        # its own row with a trailing stretch so the badge only spans its
        # own content instead of the whole card width. ───
        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)
        self._sub_label = QLabel("")
        sub_row.addWidget(self._sub_label)
        sub_row.addStretch()
        layout.addLayout(sub_row)

        self._refresh_style()

    def _build_badge_row(self) -> QHBoxLayout:
        # Just the favorite star overlaid on the image — Elemento used to
        # sit here too, but a text badge floating over the portrait
        # covered part of it; it now lives in meta_row below instead,
        # off the image entirely (see set_data/_type_label).
        top_row = QHBoxLayout()
        top_row.addStretch()

        self._fav_btn = QToolButton()
        self._fav_btn.setFixedSize(18, 18)
        self._fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; font-size: 13px; color: gold; }"
        )
        self._fav_btn.clicked.connect(self._on_fav_clicked)
        top_row.addWidget(self._fav_btn)
        return top_row

    # ─── Public API ───

    def set_data(self, name: str, level: int, category: str,
                 npc_type: str, zone_label: str, favorite: bool, image_path: str = "",
                 zone_image: QPixmap | None = None):
        self._name_label.setText(name)
        self._level_label.setText(f"Nv. {level}")
        ratio = _set_icon_or_image(self._icon_label, image_path, category_icon(category))
        if ratio:
            self._thumb.setFixedHeight(max(MIN_THUMB_H, min(MAX_THUMB_H, round(THUMB_W / ratio))))
        else:
            self._thumb.setFixedHeight(THUMB_H)
        self._type_label.setText(npc_type or "")
        if zone_image is not None and not zone_image.isNull():
            self._sub_label.setText("")
            self._sub_label.setToolTip(zone_label)
            self._sub_label.setStyleSheet("background: transparent; border: none; padding: 0;")
            self._sub_label.setPixmap(_rounded_zone_thumb(zone_image))
        elif zone_label:
            # Região set but no image available (e.g. nothing painted yet
            # and no photo uploaded) — plain muted text beats an empty badge.
            self._sub_label.setPixmap(QPixmap())
            self._sub_label.setToolTip("")
            self._sub_label.setText(zone_label)
            self._sub_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none; padding: 0;"
            )
        else:
            self._sub_label.setPixmap(QPixmap())
            self._sub_label.setToolTip("")
            self._sub_label.setText("Sem região")
            self._sub_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none; padding: 0;"
            )
        self._favorite = favorite
        self._fav_btn.setText("★" if favorite else "☆")

        # Categoria doubles as the difficulty-tier badge now — Raridade
        # (a separate field with the same Normal/Raro/Elite/Boss
        # vocabulary) was dropped as a redundant duplicate concept (see
        # mob_edit_panel.py).
        color = category_badge_color(category)
        img_border = category_image_border_color(category)
        text_color = category_tag_text_color(category)
        self._category_border_color = color
        self._rarity_chip.setText(category_label(category))
        # Solid background + customizable text color (was color-on-tinted-
        # color text, which read as a muddy blend of the category color
        # instead of a clean tag — especially noticeable on warm colors
        # like Boss' orange, which came across reddish against the dark
        # card).
        self._rarity_chip.setStyleSheet(
            f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 1px 6px; "
            f"background: {color}; color: {text_color};"
        )
        # The thumb's own border is "Cor da borda da imagem" (falls back to
        # the card border color if unset) — kept separate from the card
        # frame's border below so the two CategoryEditPanel fields actually
        # map to two different borders instead of one overwriting the other.
        self._thumb.setStyleSheet(
            f"border-radius: 8px; border: 1px solid {img_border}; "
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {color}22, stop:1 rgba(0,0,0,0.25));"
        )
        self._refresh_style()

    def set_selected(self, sel: bool):
        self._selected = sel
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            # Selection state always wins — same accent ring regardless of
            # the category's own border color, so "this card is selected"
            # stays unambiguous no matter what color the category has.
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(79,195,247,0.12); border: 1.5px solid {Colors.ACCENT}; border-radius: 10px; }}
            """)
        else:
            border_color = self._category_border_color or Colors.BORDER_SUBTLE
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {border_color}; border-radius: 10px; }}
                QFrame:hover {{ background: rgba(255,255,255,0.08); }}
            """)

    def _on_fav_clicked(self):
        self._favorite = not self._favorite
        self._fav_btn.setText("★" if self._favorite else "☆")
        self.favorite_toggled.emit(self.npc_id, self._favorite)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.npc_id)
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                         border: 1px solid {Colors.BORDER}; padding: 4px; }}
                QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
                QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
            """)
            menu.addAction("⧉ Duplicar", lambda: self.duplicate_requested.emit(self.npc_id))
            menu.addSeparator()
            menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self.npc_id))
            menu.exec(event.globalPosition().toPoint())
        super().mousePressEvent(event)


class NPCListRow(QFrame):
    """Full-width horizontal row for the "Lista" view — same signals as
    NPCCard, just a compact single-line layout instead of a grid tile."""

    selected = Signal(str)
    favorite_toggled = Signal(str, bool)
    duplicate_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, npc_id: str, parent=None):
        super().__init__(parent)
        self.npc_id = npc_id
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

        self._type_label = QLabel("")
        self._type_label.setFixedWidth(60)
        self._type_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        layout.addWidget(self._type_label)

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
        menu.addAction("⧉ Duplicar", lambda: self.duplicate_requested.emit(self.npc_id))
        menu.addSeparator()
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self.npc_id))
        menu_btn.setMenu(menu)
        layout.addWidget(menu_btn)

        self._refresh_style()

    def set_data(self, name: str, level: int, category: str,
                 npc_type: str, zone_label: str, favorite: bool, image_path: str = "",
                 zone_image: QPixmap | None = None):
        # zone_image (the região's own picture, shown image-only on
        # NPCCard's grid tile — see that class) isn't used here: this
        # compact single-line row has no room for an image badge, so it
        # keeps the plain "região name" text it always had.
        self._name_label.setText(name)
        self._level_label.setText(f"Nv. {level}")
        _set_icon_or_image(self._icon_label, image_path, category_icon(category))
        self._type_label.setText(npc_type or "—")
        self._sub_label.setText(zone_label or "Sem região")
        self._favorite = favorite
        self._fav_btn.setText("★" if favorite else "☆")
        color = category_badge_color(category)
        text_color = category_tag_text_color(category)
        self._rarity_chip.setText(category_label(category))
        self._rarity_chip.setStyleSheet(
            f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 0; "
            f"background: {color}; color: {text_color};"
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
        self.favorite_toggled.emit(self.npc_id, self._favorite)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.npc_id)
        super().mousePressEvent(event)
