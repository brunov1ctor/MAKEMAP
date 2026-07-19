"""Asset Row Card & Category Section — individual asset cards and collapsible categories."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import shiboken6
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QToolButton, QLineEdit, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QImage, QImageReader, QCursor, QPainter, QColor, QRadialGradient

from src.styles.tokens import Colors
from src.layouts.panels.assets.widgets import MiniSlider, SoundColumn, DropZone

_LIB = Path(__file__).resolve().parents[4] / "library"
_SOUNDS_DIR = _LIB / "sounds"
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}

_CARD_BG = "rgba(255, 255, 255, 0.03)"
_CARD_BORDER = "rgba(255, 255, 255, 0.08)"
_GLOW_COLOR = QColor(79, 195, 247)  # ACCENT #4FC3F7
_SEL_BG = "rgba(79, 195, 247, 0.15)"
_SEL_BORDER = "rgba(79, 195, 247, 0.8)"

_thumb_gen = None


def _get_thumbnail_generator():
    """Process-wide ThumbnailGenerator over the same on-disk cache AssetLibrary
    already maintains (128px PNGs, keyed by asset id) — avoids re-decoding full
    source images (esp. large backgrounds) every time this panel opens.
    """
    global _thumb_gen
    if _thumb_gen is None:
        from src.engines.assets.thumbnail import ThumbnailGenerator
        from src.engines.assets.library import LIBRARY_DIR
        _thumb_gen = ThumbnailGenerator(LIBRARY_DIR / "thumbnails")
    return _thumb_gen


class CardSelectionManager:
    """Singleton que coordena seleção de cards entre todas as categorias."""
    _instance: ClassVar[CardSelectionManager | None] = None
    _selected: ClassVar[list[AssetRowCard]] = []

    @classmethod
    def get(cls) -> CardSelectionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _prune(self):
        """Drop cards whose underlying C++ object is already gone.

        Nothing removes a card from `_selected` when it's destroyed (category
        repopulate, delete button, drag-drop move to another category, ...) —
        this singleton outlives any single card, so a stale reference here
        would otherwise crash the next select()/clear() that touches it.
        """
        self._selected = [c for c in self._selected if shiboken6.isValid(c)]

    def select(self, card: AssetRowCard, modifiers: Qt.KeyboardModifier,
               all_cards: list[AssetRowCard]):
        self._prune()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if shift and self._selected:
            anchor = self._selected[-1]
            if anchor in all_cards and card in all_cards:
                i0 = all_cards.index(anchor)
                i1 = all_cards.index(card)
                lo, hi = min(i0, i1), max(i0, i1)
                for c in all_cards[lo:hi + 1]:
                    if c not in self._selected:
                        self._selected.append(c)
                        c._set_selected(True)
                return

        if ctrl:
            if card in self._selected:
                self._selected.remove(card)
                card._set_selected(False)
            else:
                self._selected.append(card)
                card._set_selected(True)
        else:
            for c in self._selected:
                c._set_selected(False)
            self._selected = [card]
            card._set_selected(True)

    def clear(self):
        self._prune()
        for c in self._selected:
            c._set_selected(False)
        self._selected.clear()

    @property
    def selected(self) -> list[AssetRowCard]:
        self._prune()
        return list(self._selected)


class GhostCard(QWidget):
    """Widget flutuante que segue o mouse durante o drag."""

    def __init__(self, source: QFrame, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        # grab com fundo solido para evitar artefatos de transparencia
        raw = source.grab()
        self._pixmap = QPixmap(raw.size())
        self._pixmap.fill(QColor(11, 25, 41))  # BG_SECONDARY
        p = QPainter(self._pixmap)
        p.drawPixmap(0, 0, raw)
        p.end()
        self.resize(source.size())
        self.raise_()
        self.hide()

    def move_to(self, global_pos: QPoint, card_offset: QPoint):
        """card_offset = posicao do clique relativa ao card (drag_start)."""
        local = self.parent().mapFromGlobal(global_pos)
        self.move(local - card_offset)
        self.show()
        self.raise_()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(0.82)
        p.drawPixmap(0, 0, self._pixmap)
        p.setOpacity(1.0)
        p.setPen(QColor(79, 195, 247, 200))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        p.end()


class AssetRowCard(QFrame):
    """Card de um asset: [thumb+nome+meta+brilho/contraste] | [brush sound] | [ambient sound] [🗑]"""

    removed = Signal(str)
    settings_changed = Signal(str, int, int)

    def __init__(self, file_path: Path, category: str, parent=None):
        super().__init__(parent)
        self._path = file_path
        self._category = category
        self._drag_start: QPoint | None = None
        self._dragging = False
        self._selected = False
        self._glow_alpha = 0.0
        self._hover_pos = QPoint(0, 0)
        self.setAcceptDrops(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setStyleSheet(
            f"QFrame {{ background: {_CARD_BG}; border: 1px solid {_CARD_BORDER}; border-radius: 6px; }}"
        )

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_glow_anim)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._ghost: GhostCard | None = None
        self._drag_offset = QPoint()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(0)

        # ═══ 1/3: Info ═══
        col1 = QHBoxLayout()
        col1.setContentsMargins(0, 0, 0, 0)
        col1.setSpacing(8)

        asset_id = self._get_asset_id(file_path)

        self._thumb = QLabel()
        self._thumb.setFixedSize(64, 64)
        self._thumb.setStyleSheet("background: rgba(0,0,0,0.3); border-radius: 6px; border: none;")
        reader = QImageReader(str(file_path))
        src_size = reader.size()  # header-only read, used for metadata below either way

        pix = _get_thumbnail_generator().get_pixmap(asset_id)
        if pix is not None and not pix.isNull():
            # Cache hit — just downscale the already-small 128px cached PNG.
            pix = pix.scaled(QSize(64, 64), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        else:
            # Not cached (e.g. backgrounds, which don't go through AssetLibrary's
            # sync/thumbnail pipeline) — decode directly at thumbnail resolution
            # instead of full-res QPixmap + scaled().
            if src_size.isValid():
                reader.setScaledSize(src_size.scaled(QSize(64, 64), Qt.AspectRatioMode.KeepAspectRatio))
            thumb_image = reader.read()
            pix = QPixmap.fromImage(thumb_image) if not thumb_image.isNull() else QPixmap()

        if not pix.isNull():
            self._thumb.setPixmap(pix)
            self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col1.addWidget(self._thumb, 0)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(2)

        self._name_label = QLabel(file_path.name)
        self._name_label.setFixedHeight(16)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 8pt; background: transparent; border: none; padding: 0;")
        self._name_label.setToolTip(file_path.name)
        name_row.addWidget(self._name_label)

        self._name_edit = QLineEdit(file_path.stem)
        self._name_edit.setFixedHeight(16)
        self._name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._name_edit.setStyleSheet(
            f"QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 8pt; "
            f"background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT}; "
            f"border-radius: 3px; padding: 0 4px; }}"
        )
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.hide()
        name_row.addWidget(self._name_edit)

        self._rename_btn = QToolButton()
        self._rename_btn.setText("✎")
        self._rename_btn.setFixedSize(14, 14)
        self._rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rename_btn.setToolTip("Renomear")
        self._rename_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; margin: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ACCENT}; }}"
        )
        self._rename_btn.clicked.connect(self._toggle_rename)
        name_row.addWidget(self._rename_btn)
        name_row.addStretch()
        self._renaming = False
        info.addLayout(name_row)

        size_kb = file_path.stat().st_size / 1024
        dims = f"{src_size.width()}x{src_size.height()}" if src_size.isValid() else ""
        meta_text = f"{size_kb:.0f} KB"
        if dims:
            meta_text += f" \u2022 {dims}"
        meta_lbl = QLabel(meta_text)
        meta_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 7pt; background: transparent; border: none;")
        info.addWidget(meta_lbl)

        self._brightness = MiniSlider("Brilho", -100, 100, 0)
        self._brightness.value_changed.connect(self._update_preview)
        info.addWidget(self._brightness)
        self._contrast = MiniSlider("Contraste", -100, 100, 0)
        self._contrast.value_changed.connect(self._update_preview)
        info.addWidget(self._contrast)

        col1.addLayout(info, 1)
        row.addLayout(col1, 1)

        # ═══ 1/3: Brush Sound ═══
        col2 = QHBoxLayout()
        col2.setContentsMargins(0, 0, 0, 0)
        col2.setSpacing(0)
        col2.addStretch()
        self._brush_sound = SoundColumn(asset_id, prefix="paint")
        col2.addWidget(self._brush_sound)
        col2.addStretch()
        row.addLayout(col2, 1)

        # ═══ 1/3: Ambient Sound ═══
        col3 = QHBoxLayout()
        col3.setContentsMargins(0, 0, 0, 0)
        col3.setSpacing(0)
        col3.addStretch()
        self._ambient_sound = SoundColumn(asset_id, prefix="ambient")
        col3.addWidget(self._ambient_sound)
        col3.addStretch()
        row.addLayout(col3, 1)

        # ═══ Delete ═══
        del_btn = QToolButton()
        del_btn.setText("\U0001f5d1")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 12px; "
            f"color: {Colors.TEXT_MUTED}; border-radius: 12px; }}"
            f"QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}"
        )
        del_btn.clicked.connect(self._on_delete)
        row.addWidget(del_btn, 0)

    @staticmethod
    def _get_asset_id(file_path: Path) -> str:
        """Retorna o UUID do asset no banco, ou o stem como fallback."""
        try:
            from src.engines.assets.library import get_shared_db
            db = get_shared_db()
            row = db.execute(
                "SELECT id FROM assets WHERE source_path=?", (str(file_path),)
            ).fetchone()
            if row:
                return row["id"]
        except Exception:
            pass
        return file_path.stem

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._glow_alpha)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._glow_alpha)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self._hover_pos = event.pos()
        if self._glow_alpha > 0:
            self.update()
        if (self._drag_start is not None
                and (event.pos() - self._drag_start).manhattanLength() > 8
                and event.buttons() & Qt.MouseButton.LeftButton):
            if self._ghost is None:
                self._dragging = True
                # ghost precisa de um parent que cubra toda a área — sobe até o QScrollArea ou top-level
                host = self._find_scroll_host()
                self._ghost = GhostCard(self, host)
                self._drag_offset = self._drag_start
                self._opacity_effect.setOpacity(0.35)
                src = self._find_section()
                if src:
                    src._on_card_drag_start(str(self._path))
            if self._ghost is not None:
                global_pos = event.globalPosition().toPoint()
                self._ghost.move_to(global_pos, self._drag_offset)
                self._update_drag_hover(global_pos)
        super().mouseMoveEvent(event)

    def _find_scroll_host(self) -> QWidget:
        """Sobe na hierarquia até encontrar um QScrollArea ou usa o top-level."""
        from PySide6.QtWidgets import QScrollArea
        w = self.parent()
        while w:
            if isinstance(w, QScrollArea):
                return w.viewport()
            if w.parent() is None:
                return w
            w = w.parent()
        return self

    def _update_drag_hover(self, global_pos: QPoint):
        from PySide6.QtWidgets import QApplication
        widget = QApplication.widgetAt(global_pos)
        hover_section: CategorySection | None = None
        w = widget
        while w:
            if isinstance(w, CategorySection):
                hover_section = w
                break
            w = w.parent() if hasattr(w, 'parent') else None

        last = getattr(self, '_last_hover_section', None)
        if last is not hover_section:
            if last:
                last._remove_spacer()
                last._set_drop_highlight(False)
            self._last_hover_section = hover_section

        if hover_section:
            if hover_section._expanded:
                hover_section._set_drop_highlight(False)
                local_y = hover_section._content.mapFromGlobal(global_pos).y()
                hover_section._on_card_drag_move(local_y, str(self._path))
            else:
                # categoria fechada — anima o header
                hover_section._set_drop_highlight(True)

    def _end_drag(self):
        if self._ghost:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None
        self._opacity_effect.setOpacity(1.0)
        self._drag_start = None
        last = getattr(self, '_last_hover_section', None)
        if last:
            last._set_drop_highlight(False)
            self._last_hover_section = None

    def _set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(
                f"QFrame {{ background: {_SEL_BG}; border: 1px solid {_SEL_BORDER}; border-radius: 6px; }}"
            )
        else:
            self._on_glow_anim(self._glow_alpha)

    def _on_glow_anim(self, value):
        self._glow_alpha = value
        if self._selected:
            return
        alpha_border = int(value * 180)
        alpha_bg = int(value * 18)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,{3 + alpha_bg}); "
            f"border: 1px solid rgba(79,195,247,{alpha_border}); border-radius: 6px; }}"
        )
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._glow_alpha <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self._hover_pos.x()
        cy = self._hover_pos.y()
        grad = QRadialGradient(cx, cy, max(self.width(), self.height()) * 0.8)
        c_inner = QColor(_GLOW_COLOR)
        c_inner.setAlphaF(0.10 * self._glow_alpha)
        c_outer = QColor(_GLOW_COLOR)
        c_outer.setAlphaF(0.0)
        grad.setColorAt(0.0, c_inner)
        grad.setColorAt(1.0, c_outer)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(self.rect(), 6, 6)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._dragging = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self._ghost is not None:
            # finaliza drag — pode ser em outra categoria
            global_pos = event.globalPosition().toPoint()
            self._finish_cross_category_drop(global_pos)
        elif not self._dragging and event.button() == Qt.MouseButton.LeftButton:
            # foi clique simples — aplica seleção
            section = self._find_section()
            all_cards = section._all_cards() if section else [self]
            CardSelectionManager.get().select(self, event.modifiers(), all_cards)
        self._end_drag()
        super().mouseReleaseEvent(event)

    def _find_section(self) -> CategorySection | None:
        w = self.parent()
        while w:
            if isinstance(w, CategorySection):
                return w
            w = w.parent()
        return None

    def _finish_cross_category_drop(self, global_pos: QPoint):
        """Procura a CategorySection sob o cursor e faz o drop lá."""
        from PySide6.QtWidgets import QApplication
        widget = QApplication.widgetAt(global_pos)
        target_section: CategorySection | None = None
        w = widget
        while w:
            if isinstance(w, CategorySection):
                target_section = w
                break
            w = w.parent() if hasattr(w, 'parent') else None

        src_section = self._find_section()

        if target_section is None:
            if src_section:
                src_section._remove_spacer()
            return

        target_section._set_drop_highlight(False)

        if target_section is src_section:
            local_y = target_section._content.mapFromGlobal(global_pos).y()
            target_section._on_card_drag_drop(local_y, str(self._path))
        else:
            if src_section:
                src_section._remove_spacer()
            local_y = target_section._content.mapFromGlobal(global_pos).y()
            target_section._on_card_drop_from_outside(self, local_y)

    def _update_preview(self):
        from src.services.asset_adjustments import apply_brightness_contrast
        b = self._brightness.value()
        c = self._contrast.value()
        img = QImage(str(self._path))
        if img.isNull():
            return
        img = img.scaled(QSize(64, 64), Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        img = apply_brightness_contrast(img, b, c)
        self._thumb.setPixmap(QPixmap.fromImage(img))
        self.settings_changed.emit(str(self._path), b, c)

    def _toggle_rename(self):
        if not self._renaming:
            self._name_edit.setText(self._path.stem)
            self._name_label.hide()
            self._name_edit.show()
            self._name_edit.setFocus()
            self._name_edit.selectAll()
            self._renaming = True
        else:
            self._finish_rename()

    def _finish_rename(self):
        new_name = self._name_edit.text().strip()
        if new_name and new_name != self._path.stem:
            new_path = self._path.parent / (new_name + self._path.suffix)
            if not new_path.exists():
                self._path.rename(new_path)
                self._path = new_path
                self._name_label.setText(new_path.name)
                self._name_label.setToolTip(new_path.name)
        self._name_edit.hide()
        self._name_label.show()
        self._renaming = False

    def _on_delete(self):
        self._path.unlink(missing_ok=True)
        self.removed.emit(str(self._path))
        self.deleteLater()

    def get_settings(self) -> dict:
        return {
            "path": str(self._path),
            "brightness": self._brightness.value(),
            "contrast": self._contrast.value(),
            "brush_sound": self._brush_sound.get_config(),
            "ambient_sound": self._ambient_sound.get_config(),
        }


class CategorySection(QWidget):
    """Seção colapsável para uma categoria — header + cards dos assets."""

    delete_requested = Signal(object)  # emite self

    def __init__(self, folder: Path, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._icon = icon
        self._label = label
        self._expanded = False
        self._renaming = False
        self.setStyleSheet("background: transparent;")
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Header
        self._header = QFrame()
        self._header.setFixedHeight(32)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.02); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        self._header.mousePressEvent = lambda e: self._toggle()

        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(0)

        col1_hdr = QHBoxLayout()
        col1_hdr.setSpacing(4)
        col1_hdr.setContentsMargins(0, 0, 0, 0)
        col1_hdr.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._arrow = QLabel("▶")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 8px; background: transparent; border: none;")
        col1_hdr.addWidget(self._arrow)

        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        col1_hdr.addWidget(ic)

        self._title_label = QLabel(label)
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none; padding: 0;"
        )
        col1_hdr.addWidget(self._title_label)

        self._rename_btn = QToolButton()
        self._rename_btn.setText("✎")
        self._rename_btn.setFixedSize(14, 14)
        self._rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rename_btn.setToolTip("Renomear categoria")
        self._rename_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; margin: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ACCENT}; }}"
        )
        self._rename_btn.clicked.connect(self._toggle_rename)
        col1_hdr.addWidget(self._rename_btn)

        self._title_edit = QLineEdit(label)
        self._title_edit.setFixedHeight(20)
        self._title_edit.setMaximumWidth(100)
        self._title_edit.setStyleSheet(
            f"QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT}; "
            f"border-radius: 3px; padding: 0 4px; }}"
        )
        self._title_edit.returnPressed.connect(self._finish_rename)
        self._title_edit.hide()
        col1_hdr.addWidget(self._title_edit)

        self._count_lbl = QLabel("(0)")
        self._count_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        col1_hdr.addWidget(self._count_lbl)
        col1_hdr.addStretch()

        h_lay.addLayout(col1_hdr, 1)

        self._brush_hdr = QLabel("🖌 Brush")
        self._brush_hdr.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._brush_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brush_hdr.hide()
        h_lay.addWidget(self._brush_hdr, 1)

        self._ambient_hdr = QLabel("🔊 Sounds")
        self._ambient_hdr.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._ambient_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ambient_hdr.hide()
        h_lay.addWidget(self._ambient_hdr, 1)

        self._del_cat_btn = QToolButton()
        self._del_cat_btn.setText("🗑")
        self._del_cat_btn.setFixedSize(18, 18)
        self._del_cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._del_cat_btn.setToolTip("Deletar categoria")
        self._del_cat_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        self._del_cat_btn.clicked.connect(self._on_delete_category)
        self._del_cat_btn.hide()
        h_lay.addWidget(self._del_cat_btn, 0)

        main.addWidget(self._header)

        # Content
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent; border: none;")
        self._content.setAcceptDrops(False)
        self._content.hide()
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(8, 6, 8, 6)
        self._content_lay.setSpacing(6)
        self._drag_target_idx: int = -1
        self._spacer_anim: QVariantAnimation | None = None
        self._spacer: QWidget | None = None
        self._drop_highlight_anim: QVariantAnimation | None = None
        self._drop_highlighted = False

        self._populate()
        main.addWidget(self._content)

    def _set_drop_highlight(self, on: bool):
        """Anima o header com pulso azul quando um drag está sobre a categoria."""
        if on == self._drop_highlighted:
            return
        self._drop_highlighted = on
        if self._drop_highlight_anim:
            self._drop_highlight_anim.stop()
        if on:
            anim = QVariantAnimation(self)
            anim.setDuration(600)
            anim.setLoopCount(-1)  # infinito
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.SineCurve)
            anim.valueChanged.connect(self._apply_highlight)
            anim.start()
            self._drop_highlight_anim = anim
        else:
            self._drop_highlight_anim = None
            self._header.setStyleSheet(
                f"QFrame {{ background: rgba(255,255,255,0.02); border: none; "
                f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
            )

    def _apply_highlight(self, t: float):
        alpha = int(20 + t * 60)   # pulsa entre 20 e 80
        border_alpha = int(120 + t * 135)  # pulsa entre 120 e 255
        self._header.setStyleSheet(
            f"QFrame {{ background: rgba(79,195,247,{alpha}); border: none; "
            f"border: 2px solid rgba(79,195,247,{border_alpha}); border-radius: 4px; }}"
        )

    def _all_cards(self) -> list[AssetRowCard]:
        """Retorna todos os cards visíveis nesta seção em ordem."""
        cards = []
        for i in range(self._content_lay.count()):
            w = self._content_lay.itemAt(i).widget()
            if isinstance(w, AssetRowCard):
                cards.append(w)
        return cards

    def _on_card_drop_from_outside(self, card: AssetRowCard, local_y: float):
        """Recebe um card vindo de outra categoria: move o arquivo e recria o card."""
        src_path = card._path
        dest_path = self._folder / src_path.name
        if dest_path.exists() and dest_path != src_path:
            stem = src_path.stem
            dest_path = self._folder / f"{stem}_1{src_path.suffix}"
        try:
            src_path.rename(dest_path)
        except Exception:
            return

        new_category = self._folder.name
        try:
            from src.engines.assets.library import get_shared_db
            db = get_shared_db()
            db.execute(
                "UPDATE assets SET source_path=?, category=? WHERE source_path=?",
                (str(dest_path), new_category, str(src_path))
            )
            db.commit()
        except Exception:
            pass

        src_section = card._find_section()
        if src_section:
            src_section._content_lay.removeWidget(card)
            card.deleteLater()
            src_section._refresh()

        # expande a seção se estiver fechada
        if not self._expanded:
            self._toggle()

        target_idx = self._calc_target(local_y, str(dest_path))
        new_card = AssetRowCard(dest_path, self._label)
        new_card.removed.connect(lambda _: self._refresh())
        new_card.settings_changed.connect(self._on_adjustment)
        drop_idx = self._content_lay.count() - 1
        insert_at = min(target_idx, drop_idx)
        self._content_lay.insertWidget(insert_at, new_card)
        self._refresh()
        self._persist_order()

    def _on_card_drag_start(self, src_path: str):
        self._insert_spacer(0)

    def _on_card_drag_move(self, local_y: float, src_path: str):
        target = self._calc_target(local_y, src_path)
        if target != self._drag_target_idx:
            self._drag_target_idx = target
            self._move_spacer(target)

    def _on_card_drag_drop(self, local_y: float, src_path: str):
        spacer_idx = self._content_lay.indexOf(self._spacer) if self._spacer else -1
        self._remove_spacer()

        src_idx = None
        for i in range(self._content_lay.count() - 1):
            w = self._content_lay.itemAt(i).widget()
            if isinstance(w, AssetRowCard) and str(w._path) == src_path:
                src_idx = i
                break
        if src_idx is None:
            return

        if spacer_idx < 0:
            spacer_idx = self._calc_target(local_y, src_path)

        insert_at = spacer_idx if spacer_idx <= src_idx else spacer_idx - 1
        insert_at = max(0, min(insert_at, self._content_lay.count() - 2))

        if insert_at != src_idx:
            widget = self._content_lay.takeAt(src_idx).widget()
            self._content_lay.insertWidget(insert_at, widget)
            self._persist_order()

    def _calc_target(self, drop_y: float, src_path: str) -> int:
        n = self._content_lay.count() - 1
        for i in range(n):
            w = self._content_lay.itemAt(i).widget()
            if w is None:
                continue
            if isinstance(w, AssetRowCard) and str(w._path) == src_path:
                continue
            mid = w.y() + w.height() / 2
            if drop_y < mid:
                return i
        return max(0, n - 1)

    def _insert_spacer(self, idx: int):
        if self._spacer is not None:
            return
        self._spacer = QWidget(self._content)
        self._spacer.setStyleSheet(
            "background: rgba(79,195,247,0.9); border: none; border-radius: 1px;"
        )
        self._spacer.setFixedHeight(2)
        self._content_lay.insertWidget(idx, self._spacer)
        self._drag_target_idx = idx

    def _move_spacer(self, new_idx: int):
        if self._spacer is None:
            self._insert_spacer(new_idx)
            return
        cur_idx = self._content_lay.indexOf(self._spacer)
        if cur_idx == new_idx:
            return
        self._content_lay.removeWidget(self._spacer)
        # ajusta índice após remoção
        insert_at = new_idx if new_idx <= cur_idx else new_idx
        self._content_lay.insertWidget(insert_at, self._spacer)

    def _animate_spacer(self, start_h: int, end_h: int):
        pass  # não usado com linha fina

    def _remove_spacer(self):
        if self._spacer is None:
            return
        sp = self._spacer
        self._spacer = None
        self._drag_target_idx = -1
        if self._spacer_anim:
            self._spacer_anim.stop()
        self._content_lay.removeWidget(sp)
        sp.deleteLater()

    def _persist_order(self):
        ordered = []
        for i in range(self._content_lay.count() - 1):  # exclude DropZone
            w = self._content_lay.itemAt(i).widget()
            if isinstance(w, AssetRowCard):
                ordered.append(str(w._path))
        try:
            from src.engines.assets.library import get_shared_db
            db = get_shared_db()
            for idx, path in enumerate(ordered):
                db.execute("UPDATE assets SET sort_order = ? WHERE source_path = ?", (idx, path))
            db.commit()
        except Exception:
            pass

    def _populate(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._folder.mkdir(parents=True, exist_ok=True)
        all_files = {
            f for f in self._folder.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        }

        # Load order from DB
        ordered_files: list[Path] = []
        try:
            from src.engines.assets.library import get_shared_db
            db = get_shared_db()
            rows = db.execute(
                "SELECT source_path FROM assets WHERE source_path LIKE ? ORDER BY sort_order, name",
                (str(self._folder) + "%",)
            ).fetchall()
            for row in rows:
                p = Path(row[0])
                if p in all_files:
                    ordered_files.append(p)
                    all_files.discard(p)
        except Exception:
            pass
        # Append any files not yet in DB
        ordered_files.extend(sorted(all_files))

        self._count_lbl.setText(f"({len(ordered_files)})")
        for f in ordered_files:
            card = AssetRowCard(f, self._label)
            card.removed.connect(lambda _: self._refresh())
            card.settings_changed.connect(self._on_adjustment)
            self._content_lay.addWidget(card)

        drop = DropZone(self._folder, _SUPPORTED_IMG)
        drop.files_dropped.connect(self._on_dropped)
        self._content_lay.addWidget(drop)

    def _toggle_rename(self):
        if not self._renaming:
            self._title_edit.setText(self._label)
            self._title_label.hide()
            self._title_edit.show()
            self._title_edit.setFocus()
            self._title_edit.selectAll()
            self._renaming = True
        else:
            self._finish_rename()

    def _finish_rename(self):
        new_name = self._title_edit.text().strip()
        if new_name and new_name != self._label:
            new_folder = self._folder.parent / new_name.lower().replace(" ", "_")
            if not new_folder.exists():
                self._folder.rename(new_folder)
                self._folder = new_folder
                self._label = new_name
                self._title_label.setText(new_name)
        self._title_edit.hide()
        self._title_label.show()
        self._renaming = False

    def _on_adjustment(self, path: str, b: int, c: int):
        from src.services.asset_adjustments import AssetAdjustmentsService
        if hasattr(AssetAdjustmentsService, '_instance'):
            AssetAdjustmentsService._instance.set(path, b, c)

    def _on_dropped(self, paths: list):
        idx = self._content_lay.count() - 1
        for p in paths:
            card = AssetRowCard(p, self._label)
            card.removed.connect(lambda _: self._refresh())
            self._content_lay.insertWidget(idx, card)
            idx += 1
        self._refresh()

    def _refresh(self):
        count = len([
            f for f in self._folder.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        ])
        self._count_lbl.setText(f"({count})")

    def _toggle(self):
        self._expanded = not self._expanded
        self._arrow.setText("▼" if self._expanded else "▶")
        self._content.setVisible(self._expanded)
        self._brush_hdr.setVisible(self._expanded)
        self._ambient_hdr.setVisible(self._expanded)
        self._del_cat_btn.setVisible(self._expanded)

    def _on_delete_category(self):
        from PySide6.QtWidgets import QMessageBox
        assets = [
            f for f in self._folder.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        ]
        if assets:
            QMessageBox.warning(
                self, "Categoria não vazia",
                f"A categoria '{self._label}' possui {len(assets)} asset(s).\n"
                "Mova ou delete os assets antes de remover a categoria."
            )
            return
        reply = QMessageBox.question(
            self, "Deletar categoria",
            f"Deletar a categoria '{self._label}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            import shutil
            shutil.rmtree(self._folder, ignore_errors=True)
            self.delete_requested.emit(self)
