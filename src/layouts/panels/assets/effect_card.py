"""EffectCard / EffectsConfigSection — configuration UI for the Brush
tool's animated effects (Névoa, Poeira, ... — see engines.map.brush_effects.
ANIMATED_EFFECTS). Unlike CategorySection, this is NOT a folder the user
drops arbitrary files into: the set of cards is fixed (one per code-defined
effect key), since that's the whole universe of effects the Brush can
paint — nothing here can be added or removed, only configured (image,
brush/ambient sound, brilho/contraste).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget, QFileDialog,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImage

from src.styles.tokens import Colors
from src.engines.assets.effect_configs import get_effect_config, set_effect_image, set_effect_adjustments
from src.engines.map.brush_effects import ANIMATED_EFFECTS
from src.canvas.tools.brush_tool import BrushTool
from src.layouts.panels.assets.widgets import MiniSlider, SoundColumn
from src.layouts.panels.mobs.edit_widgets import _DropImageButton
from src.services.asset_adjustments import apply_brightness_contrast

_THUMB_SIZE = 48


class EffectCard(QFrame):
    """One row per animated effect key — same 3-column shape as
    AssetRowCard (info | brush sound | ambient sound), just with a pick/
    drop image button instead of a real library file thumbnail, since
    there's no file on disk to read dimensions/size from."""

    _CARD_BG = "rgba(255, 255, 255, 0.03)"
    _CARD_BORDER = "rgba(255, 255, 255, 0.08)"

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._image_path = ""
        self.setStyleSheet(
            f"QFrame {{ background: {self._CARD_BG}; border: 1px solid {self._CARD_BORDER}; border-radius: 6px; }}"
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(0)

        # ═══ 1/3: Info ═══
        col1 = QHBoxLayout()
        col1.setContentsMargins(0, 0, 0, 0)
        col1.setSpacing(8)

        self._thumb = _DropImageButton()
        self._thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._thumb.setIconSize(QSize(_THUMB_SIZE, _THUMB_SIZE))
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.setToolTip("Clique ou arraste uma imagem")
        self._thumb.setStyleSheet(f"""
            QToolButton {{ border-radius: 6px; border: 1px dashed {Colors.BORDER_SUBTLE};
                background: rgba(255,255,255,0.05); font-size: 18px; color: {Colors.TEXT_MUTED}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        self._thumb.setText("✨")
        self._thumb.clicked.connect(self._on_pick_image)
        self._thumb.image_dropped.connect(self._on_image_chosen)
        col1.addWidget(self._thumb, 0)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)

        name_lbl = QLabel(key)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; background: transparent; border: none;")
        info.addWidget(name_lbl)

        self._brightness = MiniSlider("Brilho", -100, 100, 0)
        self._brightness.value_changed.connect(self._on_adjustment_changed)
        info.addWidget(self._brightness)
        self._contrast = MiniSlider("Contraste", -100, 100, 0)
        self._contrast.value_changed.connect(self._on_adjustment_changed)
        info.addWidget(self._contrast)

        col1.addLayout(info, 1)
        row.addLayout(col1, 1)

        # ═══ 1/3: Brush Sound ═══
        col2 = QHBoxLayout()
        col2.setContentsMargins(0, 0, 0, 0)
        col2.addStretch()
        asset_id = f"{BrushTool.EFFECT_ASSET_PREFIX}{key}"
        col2.addWidget(SoundColumn(asset_id, prefix="paint"))
        col2.addStretch()
        row.addLayout(col2, 1)

        # ═══ 1/3: Ambient Sound ═══
        col3 = QHBoxLayout()
        col3.setContentsMargins(0, 0, 0, 0)
        col3.addStretch()
        col3.addWidget(SoundColumn(asset_id, prefix="ambient"))
        col3.addStretch()
        row.addLayout(col3, 1)

        self._load()

    def _load(self):
        cfg = get_effect_config(self._key)
        self._image_path = cfg["image_path"]
        self._brightness.blockSignals(True)
        self._brightness.set_value(cfg["brightness"])
        self._brightness.blockSignals(False)
        self._contrast.blockSignals(True)
        self._contrast.set_value(cfg["contrast"])
        self._contrast.blockSignals(False)
        self._refresh_thumb()

    def _refresh_thumb(self):
        img = QImage(self._image_path) if self._image_path else QImage()
        if img.isNull():
            self._thumb.set_cover_pixmap(None)
            self._thumb.setText("✨")
            return
        img = apply_brightness_contrast(img, self._brightness.value(), self._contrast.value())
        self._thumb.setText("")
        self._thumb.set_cover_pixmap(QPixmap.fromImage(img))

    def _on_pick_image(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Selecionar Imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
        if path:
            self._on_image_chosen(path)

    def _on_image_chosen(self, path: str):
        stored = set_effect_image(self._key, path)
        self._image_path = stored
        self._refresh_thumb()

    def _on_adjustment_changed(self, _value: int):
        set_effect_adjustments(self._key, self._brightness.value(), self._contrast.value())
        self._refresh_thumb()


class EffectsConfigSection(QWidget):
    """One EffectCard per ANIMATED_EFFECTS key, filterable by name — same
    search-then-list shape as CategorySection's card list, minus drag/
    drop reordering (there's no "order" here, these are fixed keys)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Buscar efeito...")
        self._search.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px; padding: 6px 8px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt; }}
        """)
        self._search.textChanged.connect(self._apply_filter)
        outer.addWidget(self._search)

        self._cards: dict[str, EffectCard] = {}
        for key in ANIMATED_EFFECTS:
            card = EffectCard(key)
            outer.addWidget(card)
            self._cards[key] = card

        outer.addStretch()

    def _apply_filter(self, text: str):
        query = text.strip().lower()
        for key, card in self._cards.items():
            card.setVisible(not query or query in key.lower())
