"""AssetEffectsPanel — paint which regions of an asset DEFINITION (not a
placed instance) get a special visual effect (see src/engines/
asset_effects.py). Opened from a card's "⋮" button (see AssetRowCard /
AssetEffectsMediator). A single shared instance, floating INSIDE the app
(same "no window outside the app" rule as every other picker here) —
reused for whichever asset's card triggers it, positioned by MainLayout,
not a QDialog. Its own color picker (_EffectConfigBlock) is inline, not a
second riding panel like ColorCustomizePanel elsewhere — see that class's
docstring.

The paintable grid (EffectGridPaint) mirrors PixelGridPaint's click/drag
mechanic (src/layouts/panels/color_customize_panel.py) — same interaction,
but each of the 5 effect types is its own independent, overlappable layer
instead of one exclusive value per cell, and painting is a free circular
brush (see BRUSH_RADIUS) instead of one-cell-at-a-time.

Effects are picked from cards grouped by category (_EFFECT_CATEGORIES) to
set the current paint brush — clicking a card also loads its
Cor/Intensidade/Raio/Brilho + visibility/blend/opacity into
_EffectConfigBlock, right below the palette, regardless of whether that
effect has been painted yet. The "CAMADAS" list (right column) is a
separate, simpler thing: just a glance list of whichever effects actually
have something painted, for quickly re-selecting one or clearing it — not
a second place to edit the same fields. The whole panel has no fixed
height — it sizes to whatever's actually visible (see AssetEffectsMediator
/panel_layout_engine.py's use of PanelManager._content_height), so an
asset with 0 painted effects doesn't carry the same tall panel as one with
several."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QToolButton, QComboBox, QSlider, QWidget, QLineEdit,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QImage, QPixmap, QCursor

from src.styles.tokens import Colors, combo_popup_qss
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.items.editor_base import SquareCheck
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare
from src.engines.asset_effects import (
    ASSET_EFFECT_TYPES, BLEND_MODES, EFFECT_GRID_SIZE, PARAMS, PARAM_MIN, PARAM_MAX, PARAM_DEFAULT,
    effect_label, empty_layers, normalize_layers,
)

_PREVIEW_COLORS = {
    "emissivo": QColor(255, 220, 150, 210),
    "aura": QColor(150, 200, 255, 210),
    "glitter": QColor(255, 255, 255, 210),
    "fumaca": QColor(150, 130, 170, 210),
    "distorcao": QColor(180, 220, 255, 210),
}

# (category label, [effect keys]) — groups the 5 existing effects into the
# same two-section shape as the reference layout (Iluminação / Aura-Magia),
# without inventing new effect types.
_EFFECT_CATEGORIES: list[tuple[str, list[str]]] = [
    ("ILUMINAÇÃO", ["emissivo", "glitter"]),
    ("AURA / MAGIA", ["aura", "fumaca", "distorcao"]),
]


def _effect_icon(key: str) -> str:
    for k, icon, _label in ASSET_EFFECT_TYPES:
        if k == key:
            return icon
    return "⌫"


class EffectGridPaint(QFrame):
    """Free-form, spray-style paint surface. Underneath there's still a
    fine EFFECT_GRID_SIZE² boolean mask per layer (kept simple for JSON
    round-tripping and reused as-is by AssetEffectsOverlay), but painting
    covers several cells at once around the exact pointer position
    (BRUSH_RADIUS) and rendering draws each layer as ONE smooth-scaled
    image instead of many small flat-filled rectangles — drawing per-cell
    rects left visible seams at cell boundaries (adjacent translucent
    fills double-blending at their shared edge), which read as a
    checkerboard even with no grid lines actually drawn. A single bilinear-
    scaled image has no seams and naturally softens the mask's edges into
    an organic blob, same spirit as the Brush tool's own circular stamps."""

    painted = Signal()
    BRUSH_RADIUS = 2.6  # cells — footprint of one dab, in grid-cell units

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = self.rows = EFFECT_GRID_SIZE
        self.layers: dict[str, dict] = empty_layers()
        self._brush = "emissivo"
        self._thumbnail: QPixmap | None = None
        self.setFixedSize(280, 280)
        self.setStyleSheet(f"border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;")
        self._update_cursor()

    def set_brush(self, key: str):
        self._brush = key
        self._update_cursor()

    def _update_cursor(self):
        """Mouse cursor badge showing which effect is about to be painted
        (or the eraser) instead of a generic crosshair — same idea as a
        paint app showing the active tool on the cursor itself."""
        icon = _effect_icon(self._brush) if self._brush else "⌫"
        size = 26
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = p.font()
        font.setPointSize(15)
        p.setFont(font)
        p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, icon)
        p.end()
        self.setCursor(QCursor(pixmap, size // 2, size // 2))

    def set_thumbnail(self, thumbnail: QPixmap | None):
        self._thumbnail = thumbnail
        self.update()

    def load(self, layers: dict[str, dict]):
        self.layers = normalize_layers(layers)
        self.update()

    def clear_layer(self, key: str):
        if key in self.layers:
            self.layers[key] = {"cells": [False] * (self.cols * self.rows), **{
                k: v for k, v in self.layers[key].items() if k != "cells"
            }}
            self.update()
            self.painted.emit()

    def _paint_at(self, pos):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        # Exact fractional position in cell units — NOT rounded/snapped to
        # one cell — so the dab is centered wherever the pointer actually
        # is, same continuous feel as a spray can rather than a stamp tool.
        cx = pos.x() * self.cols / w
        cy = pos.y() * self.rows / h
        r = self.BRUSH_RADIUS
        x0, x1 = max(0, int(cx - r)), min(self.cols - 1, int(cx + r))
        y0, y1 = max(0, int(cy - r)), min(self.rows - 1, int(cy + r))
        erasing = not self._brush
        layer = None if erasing else self.layers[self._brush]
        changed = False
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                dx, dy = (x + 0.5) - cx, (y + 0.5) - cy
                if dx * dx + dy * dy > r * r:
                    continue
                idx = y * self.cols + x
                if erasing:
                    # Clears this cell from every layer, regardless of
                    # which effect(s) are painted there.
                    for other in self.layers.values():
                        if other["cells"][idx]:
                            other["cells"][idx] = False
                            changed = True
                elif not layer["cells"][idx]:
                    layer["cells"][idx] = True
                    changed = True
        if changed:
            self.update()
            self.painted.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._paint_at(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._paint_at(event.position())

    def _layer_mask_image(self, key: str, color: QColor) -> QImage:
        """One small (cols x rows) ARGB image with `color` wherever that
        layer's cells are painted — scaled up with smooth bilinear
        filtering in paintEvent, which both hides the underlying grid
        resolution AND naturally softens the mask's edges."""
        img = QImage(self.cols, self.rows, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))
        cells = self.layers[key]["cells"]
        for y in range(self.rows):
            row_off = y * self.cols
            for x in range(self.cols):
                if cells[row_off + x]:
                    img.setPixelColor(x, y, color)
        return img

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

        # Every layer painted stacks (SourceOver, the QPainter default) —
        # this is the "overlap allowed" preview: two effects sharing a
        # region show both tints blended instead of one replacing the
        # other. Each layer is ONE smooth-scaled image, not per-cell
        # rects, so there are no seams between adjacent painted cells.
        for key, _icon, _label in ASSET_EFFECT_TYPES:
            layer = self.layers[key]
            if not layer["visible"] or not any(layer["cells"]):
                continue
            # The layer's own configured color (see _LayerRow's
            # ColorField) — falls back to the fixed preview tint only if
            # somehow missing/invalid.
            color = QColor(layer.get("color", ""))
            if not color.isValid():
                color = _PREVIEW_COLORS.get(key, QColor(255, 255, 255, 160))
            else:
                color.setAlpha(210)
            mask = self._layer_mask_image(key, color)
            scaled = mask.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawImage(0, 0, scaled)
        p.end()


class _EffectCard(QFrame):
    """One effect in the palette — icon + name, grouped under a category
    label (see _EFFECT_CATEGORIES) instead of a flat row of tiny icon-only
    buttons. Selection state is painted manually (set_selected), not a
    QButtonGroup — AssetEffectsPanel owns exclusivity across cards AND the
    separate eraser button. Both child labels are WA_TransparentForMouseEvents
    so a click anywhere on the card (not just its unlabeled margin) reaches
    THIS frame's mousePressEvent — a plain QLabel would otherwise eat the
    click itself and never let it bubble up, same fix toolbar.py's drag
    grip already needed for the same reason."""

    clicked = Signal(str)

    def __init__(self, key: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(54, 46)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 2)
        lay.setSpacing(1)
        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        icon_lbl.setStyleSheet("font-size: 15px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)
        name_lbl = QLabel(label)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        name_lbl.setStyleSheet(f"font-size: 6.5px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;")
        lay.addWidget(name_lbl)
        self._refresh_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{ border: 1px solid {Colors.ACCENT}; border-radius: 8px; background: {Colors.ACCENT_DIM}; }}
                QLabel {{ background: transparent; border: none; }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; background: rgba(255,255,255,0.04); }}
                QLabel {{ background: transparent; border: none; }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class _LayerRow(QFrame):
    """One row in the "CAMADAS" list — a glance-only entry for an effect
    that actually has something painted (see
    AssetEffectsPanel._refresh_layers_list, which only lists painted
    effects here). Just icon/name + clear; clicking anywhere on the row
    (except 🗑) re-selects that effect's card, which is where the actual
    editing happens (see _EffectConfigBlock, below the palette) — CAMADAS'
    job is "what's painted right now", not a second place to edit the same
    fields, which would need to stay in sync with the config block on
    every slider tick for no real benefit."""

    clicked = Signal(str)
    clear_requested = Signal(str)

    def __init__(self, key: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)

        name_lbl = QLabel(f"{icon} {label}")
        name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; background: transparent; border: none;")
        row.addWidget(name_lbl, 1)

        clear_btn = QToolButton()
        clear_btn.setText("🗑")
        clear_btn.setFixedSize(20, 20)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("Limpar esta camada")
        clear_btn.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        clear_btn.clicked.connect(lambda: self.clear_requested.emit(self.key))
        row.addWidget(clear_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class _EffectConfigBlock(QFrame):
    """Cor/Intensidade/Raio/Brilho + visibility/blend/opacity for whichever
    effect card is currently selected in EFEITOS — right below the
    palette, and shown regardless of whether that effect has been painted
    yet, so clicking ANY card always reveals its params (painting isn't a
    prerequisite for configuring how an effect will look once it IS
    painted). One persistent widget, repopulated via load() on every card
    click rather than destroyed/recreated — CAMADAS (right column) stays a
    simple list of only the effects that actually have paint on them."""

    changed = Signal()
    clear_requested = Signal()
    picker_toggled = Signal()  # opened/closed the inline HSV picker — a resize, not a value change

    def __init__(self, parent=None):
        super().__init__(parent)
        self.key = ""
        self._color = "#FFFFFF"
        self._hsv = [0, 0, 100]
        self.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; background: transparent; border: none;")
        header.addWidget(self._title_lbl, 1)
        self._vis_btn = QToolButton()
        self._vis_btn.setText("👁")
        self._vis_btn.setCheckable(True)
        self._vis_btn.setFixedSize(20, 20)
        self._vis_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vis_btn.setToolTip("Mostrar/ocultar esta camada")
        self._vis_btn.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:checked {{ color: {Colors.ACCENT}; }}
        """)
        self._vis_btn.toggled.connect(self._on_changed)
        header.addWidget(self._vis_btn)
        clear_btn = QToolButton()
        clear_btn.setText("🗑")
        clear_btn.setFixedSize(20, 20)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("Limpar esta camada")
        clear_btn.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 10px; color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; }}
        """)
        clear_btn.clicked.connect(self.clear_requested.emit)
        header.addWidget(clear_btn)
        outer.addLayout(header)

        bo_row = QHBoxLayout()
        bo_row.setSpacing(8)
        self._blend_combo = QComboBox()
        self._blend_combo.setFixedWidth(78)
        self._blend_combo.setToolTip(
            "Como ESTA camada se mistura com o que já está desenhado embaixo dela "
            "(o asset e as outras camadas) — não afeta onde cada efeito está pintado, "
            "que continua independente. Normal = sobrepõe com transparência normal. "
            "Aditivo = soma luz (fica mais claro/brilhante), bom para Emissivo/Aura."
        )
        for blend_key, blend_label in BLEND_MODES:
            self._blend_combo.addItem(blend_label, blend_key)
        self._blend_combo.setStyleSheet(f"""
            QComboBox {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 2px 6px; font-size: 9px; }}
            {combo_popup_qss()}
        """)
        self._blend_combo.currentIndexChanged.connect(self._on_changed)
        bo_row.addWidget(self._blend_combo)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setToolTip("Opacidade da camada")
        self._opacity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: {Colors.BG_TERTIARY}; height: 3px; border-radius: 1px; }}
            QSlider::handle:horizontal {{ background: {Colors.ACCENT}; width: 8px; height: 8px; margin: -3px 0; border-radius: 4px; }}
        """)
        self._opacity_lbl = QLabel("100%")
        self._opacity_lbl.setFixedWidth(32)
        self._opacity_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
        self._opacity_slider.valueChanged.connect(lambda v: self._opacity_lbl.setText(f"{v}%"))
        self._opacity_slider.valueChanged.connect(self._on_changed)
        bo_row.addWidget(self._opacity_slider, 1)
        bo_row.addWidget(self._opacity_lbl)
        outer.addLayout(bo_row)

        # Cor — a compact inline picker (swatch + hex + collapsible hue/
        # sat-val), not a button that opens ANOTHER floating panel. Toggled
        # open/closed by clicking the swatch; stays inside this same block,
        # inside this same panel.
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        color_lbl = QLabel("Cor")
        color_lbl.setFixedWidth(58)
        color_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        color_row.addWidget(color_lbl)
        self._swatch_btn = QToolButton()
        self._swatch_btn.setFixedSize(24, 20)
        self._swatch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch_btn.setToolTip("Clique para escolher a cor")
        self._swatch_btn.clicked.connect(self._toggle_picker)
        color_row.addWidget(self._swatch_btn)
        self._hex_input = QLineEdit("FFFFFF")
        self._hex_input.setMaxLength(6)
        self._hex_input.setFixedWidth(64)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 9px; padding: 3px 6px; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        color_row.addWidget(self._hex_input)
        color_row.addStretch()
        outer.addLayout(color_row)

        self._picker_frame = QFrame()
        self._picker_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        picker_lay = QVBoxLayout(self._picker_frame)
        picker_lay.setContentsMargins(0, 4, 0, 0)
        picker_lay.setSpacing(4)
        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(14)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        picker_lay.addWidget(self._hue_bar)
        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(70)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        picker_lay.addWidget(self._sv_square)
        outer.addWidget(self._picker_frame)
        self._picker_frame.setVisible(False)
        self._set_color("#FFFFFF", emit=False)

        self._param_sliders: dict[str, QSlider] = {}
        for attr, param_label in PARAMS:
            prow = QHBoxLayout()
            prow.setSpacing(8)
            plbl = QLabel(param_label)
            plbl.setFixedWidth(58)
            plbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
            prow.addWidget(plbl)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(round(PARAM_MIN), round(PARAM_MAX))
            slider.setValue(round(PARAM_DEFAULT))
            slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{ background: {Colors.BG_TERTIARY}; height: 3px; border-radius: 1px; }}
                QSlider::handle:horizontal {{ background: {Colors.ACCENT}; width: 8px; height: 8px; margin: -3px 0; border-radius: 4px; }}
            """)
            val_lbl = QLabel(str(round(PARAM_DEFAULT)))
            val_lbl.setFixedWidth(20)
            val_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
            slider.valueChanged.connect(lambda v, vl=val_lbl: vl.setText(str(v)))
            slider.valueChanged.connect(self._on_changed)
            prow.addWidget(slider, 1)
            prow.addWidget(val_lbl)
            outer.addLayout(prow)
            self._param_sliders[attr] = slider

    def load(self, key: str, icon: str, label: str, layer: dict):
        self.key = key
        self._title_lbl.setText(f"{icon} {label}")
        widgets = [self._vis_btn, self._blend_combo, self._opacity_slider, *self._param_sliders.values()]
        for w in widgets:
            w.blockSignals(True)
        self._vis_btn.setChecked(layer["visible"])
        idx = next((i for i, (k, _l) in enumerate(BLEND_MODES) if k == layer["blend"]), 0)
        self._blend_combo.setCurrentIndex(idx)
        self._opacity_slider.setValue(layer["opacity"])
        self._opacity_lbl.setText(f"{layer['opacity']}%")
        for attr, slider in self._param_sliders.items():
            slider.setValue(round(layer.get(attr, PARAM_DEFAULT)))
        for w in widgets:
            w.blockSignals(False)
        self._set_color(layer.get("color", "#FFFFFF"), emit=False)

    def _on_changed(self, *_args):
        self.changed.emit()

    def apply_to(self, layer: dict):
        layer["visible"] = self._vis_btn.isChecked()
        layer["blend"] = self._blend_combo.currentData()
        layer["opacity"] = self._opacity_slider.value()
        layer["color"] = self._color
        for attr, slider in self._param_sliders.items():
            layer[attr] = float(slider.value())

    # ─── Inline color picker ───

    def _toggle_picker(self):
        self._picker_frame.setVisible(not self._picker_frame.isVisible())
        self.picker_toggled.emit()

    def _set_color(self, hex_color: str, emit: bool):
        color = QColor(hex_color)
        if not color.isValid():
            return
        self._color = color.name()
        h = color.hsvHue() if color.hsvHue() >= 0 else 0
        self._hsv = [h, color.hsvSaturation() * 100 // 255, color.value() * 100 // 255]
        self._hue_bar.blockSignals(True)
        self._hue_bar.set_hue(h)
        self._hue_bar.blockSignals(False)
        self._sv_square.blockSignals(True)
        self._sv_square.set_hue(h)
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sv_square.blockSignals(False)
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._color.lstrip("#"))
        self._hex_input.blockSignals(False)
        self._swatch_btn.setStyleSheet(
            f"QToolButton {{ background: {self._color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}"
        )
        if emit:
            self._on_changed()

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1], self._hsv[2] = s, v
        self._apply_hsv()

    def _apply_hsv(self):
        color = QColor.fromHsv(self._hsv[0], self._hsv[1] * 255 // 100, self._hsv[2] * 255 // 100)
        self._set_color(color.name(), emit=True)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in text):
            self._set_color(f"#{text}", emit=True)


class AssetEffectsPanel(QFrame):
    PANEL_WIDTH = 620

    saved = Signal(str, dict)  # asset_id, layers
    foam_toggled = Signal(str, bool)  # asset_id, enabled
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.asset_id = ""
        # Width stays fixed (two-column layout below), but NOT height —
        # this panel's content genuinely varies a lot (0 to 5 painted
        # effects, each independently expandable), so a fixed height
        # either wasted a lot of empty space or clipped content depending
        # on what's actually shown. See panel_layout_engine.py, which
        # sizes this via PanelManager._content_height() same as every
        # other panel here that isn't a fixed shape.
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        # Painting/config changes persist on their own, shortly after the
        # last stroke — same "close and reopen, it's as I left it"
        # expectation as the ★ favorite/🌊 Maresia toggles elsewhere in
        # this panel, instead of requiring an explicit Salvar click first.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(400)
        self._autosave_timer.timeout.connect(self._on_save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Title bar doubles as a drag handle — this panel floats centered
        # by default (see panel_layout_engine.py) but nothing here stops
        # the user from wanting it somewhere else (e.g. out of the way of
        # the asset it's editing); drag it like a real window titlebar.
        # WA_TransparentForMouseEvents on the title label lets a click
        # anywhere on the text still reach this frame's own drag handlers
        # (same fix _LayerRow's header/_EffectCard needed for the same
        # reason) — only close_btn, a real button, opts out.
        self._custom_pos: object = None  # QPoint once user-dragged, else auto-centered
        self._drag_last_global = None
        header_frame = QFrame()
        header_frame.setCursor(Qt.CursorShape.SizeAllCursor)
        header_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self._title = QLabel("✨ Efeitos do Asset")
        self._title.setWordWrap(True)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        header.addWidget(self._title, 1)
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self._flush_and_close)
        header.addWidget(close_btn)
        header_frame.mousePressEvent = self._on_header_press
        header_frame.mouseMoveEvent = self._on_header_move
        header_frame.mouseReleaseEvent = self._on_header_release
        layout.addWidget(header_frame)

        hint = QLabel("Pinte as regiões de cada efeito — eles se sobrepõem livremente. Clique numa camada em CAMADAS pra abrir os parâmetros dela.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10pt; background: transparent; border: none;")
        layout.addWidget(hint)

        # 2x2 grid — an actual QGridLayout, not nested boxes, so each
        # quadrant gets its own non-overlapping cell instead of relying on
        # stretches/margins lining up by coincidence (which is what let
        # CAMADAS visually collide with the asset image before): top row
        # is EFEITOS (palette) + the asset/paint grid, the two things you
        # actually look at while painting; bottom row is the secondary
        # stuff (Borracha/Maresia, and CAMADAS) — given row stretch 0 so it
        # only ever takes its own natural minimal height, deliberately
        # smaller/less prominent than the top row.
        body = QGridLayout()
        body.setHorizontalSpacing(10)
        body.setVerticalSpacing(6)
        body.setColumnMinimumWidth(0, 230)
        body.setColumnStretch(0, 0)
        body.setColumnStretch(1, 1)
        body.setRowStretch(0, 1)
        body.setRowStretch(1, 0)
        layout.addLayout(body)

        left_col = QWidget()
        left_col.setFixedWidth(230)
        left_lay = QVBoxLayout(left_col)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)
        body.addWidget(left_col, 0, 0)

        efeitos_lbl = QLabel("EFEITOS")
        efeitos_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        left_lay.addWidget(efeitos_lbl)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Buscar efeito...")
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 4px 8px; font-size: 10px; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self._search_edit, 1)

        # Borracha rides next to the search box instead of down in the
        # bottom-left cell — it's a palette-level tool (picks what
        # painting does next, same as an effect card), not a secondary/
        # less-relevant control, so it belongs up with EFEITOS.
        self._erase_btn = QToolButton()
        self._erase_btn.setText("⌫")
        self._erase_btn.setToolTip("Borracha — apaga de todas as camadas na área pintada")
        self._erase_btn.setCheckable(True)
        self._erase_btn.setFixedSize(26, 26)
        self._erase_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._erase_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px;
                background: rgba(255,255,255,0.04); color: {Colors.TEXT_SECONDARY}; font-size: 12px; }}
            QToolButton:hover {{ border-color: {Colors.BORDER_HOVER}; }}
            QToolButton:checked {{ border-color: {Colors.WARNING}; background: rgba(255,167,38,0.15); color: {Colors.WARNING}; }}
        """)
        self._erase_btn.clicked.connect(self._on_eraser_selected)
        search_row.addWidget(self._erase_btn)
        left_lay.addLayout(search_row)

        # ── Paleta: cards agrupados por categoria (escolhe o pincel) ──
        self._current_brush_key = "emissivo"
        self._effect_cards: dict[str, _EffectCard] = {}
        self._category_sections: list[tuple[QLabel, QHBoxLayout]] = []
        for cat_label, keys in _EFFECT_CATEGORIES:
            cat_lbl = QLabel(cat_label)
            cat_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
            left_lay.addWidget(cat_lbl)
            cat_row = QHBoxLayout()
            cat_row.setSpacing(6)
            for key in keys:
                card = _EffectCard(key, _effect_icon(key), effect_label(key))
                card.clicked.connect(self._on_effect_selected)
                cat_row.addWidget(card)
                self._effect_cards[key] = card
            cat_row.addStretch()
            left_lay.addLayout(cat_row)
            self._category_sections.append((cat_lbl, cat_row))

        # Params for whichever card is currently selected — right below
        # the palette, always showing (see _on_effect_selected), not
        # gated behind whether that effect has been painted yet.
        self._config_block = _EffectConfigBlock()
        self._config_block.changed.connect(self._on_config_changed)
        self._config_block.clear_requested.connect(self._on_config_clear)
        self._config_block.picker_toggled.connect(self._resize_to_content)
        left_lay.addWidget(self._config_block)

        left_lay.addStretch()

        # ── Bottom-left (row 1, less relevant): Maresia ──
        # Maximum vertical policy + AlignTop: this cell must never stretch
        # to match row 1's height (it did before, since a plain QWidget's
        # default Preferred policy still lets QGridLayout grow it to fill
        # a taller row) — that's exactly what showed up as a big empty box
        # here once CAMADAS' row made row 1 tall.
        left_bottom = QWidget()
        left_bottom.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        left_bottom_lay = QVBoxLayout(left_bottom)
        left_bottom_lay.setContentsMargins(0, 0, 0, 0)
        left_bottom_lay.setSpacing(4)
        body.addWidget(left_bottom, 1, 0, Qt.AlignmentFlag.AlignTop)

        # "🌊 Maresia" — só aparece para assets da categoria "water" (ver
        # load_asset). O halo de espuma onde água encosta em terra (Brush
        # tool, _apply_shoreline_blend) fica bem pra mar, mas estranho pra
        # rio — este toggle deixa desligar por asset, ao contrário de tudo-
        # ou-nada. Muda na hora (como o ★ favoritar), não espera "Salvar".
        self._foam_row = QFrame()
        self._foam_row.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        foam_lay = QHBoxLayout(self._foam_row)
        foam_lay.setContentsMargins(10, 6, 10, 6)
        foam_lay.setSpacing(8)
        foam_label = QLabel("🌊 Maresia")
        foam_label.setToolTip("Maresia (espuma junto à terra)")
        foam_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; background: transparent; border: none;")
        foam_lay.addWidget(foam_label, 1)
        self._foam_check = SquareCheck(checked=True)
        self._foam_check.toggled.connect(self._on_foam_toggled)
        foam_lay.addWidget(self._foam_check)
        left_bottom_lay.addWidget(self._foam_row)
        self._foam_row.hide()

        # ── Top-right (row 0): a imagem do asset + a grade de pintura ──
        grid_cell = QWidget()
        grid_cell_lay = QHBoxLayout(grid_cell)
        grid_cell_lay.setContentsMargins(0, 0, 0, 0)
        grid_cell_lay.addStretch()
        self.grid = EffectGridPaint()
        self.grid.painted.connect(self._on_layers_mutated)
        grid_cell_lay.addWidget(self.grid)
        grid_cell_lay.addStretch()
        body.addWidget(grid_cell, 0, 1)

        # ── Bottom-right (row 1, less relevant): CAMADAS — own cell, so it
        # can never visually collide with the asset image above it the way
        # it could when both shared one QVBoxLayout and the grid's stretch-
        # centered row left ambiguous leftover space for CAMADAS to bleed
        # into. ──
        right_bottom = QWidget()
        right_bottom.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        right_bottom_lay = QVBoxLayout(right_bottom)
        right_bottom_lay.setContentsMargins(0, 0, 0, 0)
        right_bottom_lay.setSpacing(4)
        body.addWidget(right_bottom, 1, 1, Qt.AlignmentFlag.AlignTop)

        camadas_lbl = QLabel("CAMADAS")
        camadas_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        right_bottom_lay.addWidget(camadas_lbl)

        # Plain layout, NOT a QScrollArea — the whole point is that this
        # only takes as much height as the rows actually visible need (0
        # painted ≈ one small label, all 5 painted ≈ a taller column), and
        # the panel itself grows/shrinks to match instead of carrying a
        # fixed-height scroll viewport regardless. Only effects that
        # actually have something painted get a row here — editing params
        # doesn't happen here at all (see _EffectConfigBlock, above), so
        # there's no reason to list effects nothing's been painted on yet.
        self._layers_list = QVBoxLayout()
        self._layers_list.setContentsMargins(0, 0, 0, 0)
        self._layers_list.setSpacing(4)
        right_bottom_lay.addLayout(self._layers_list)
        self._layers_empty_lbl = QLabel("Nenhum efeito pintado ainda.")
        self._layers_empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        self._layer_rows: dict[str, _LayerRow] = {}

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        close2_btn = QToolButton()
        close2_btn.setText("Fechar")
        close2_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close2_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_SECONDARY}; background: rgba(255,255,255,0.04); padding: 5px 12px; font-size: 10px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        close2_btn.clicked.connect(self._flush_and_close)
        btn_row.addWidget(close2_btn)

        save_btn = QToolButton()
        save_btn.setText("Salvar")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QToolButton {{ border: 1px solid {Colors.ACCENT}; border-radius: 4px;
                color: {Colors.TEXT_PRIMARY}; background: {Colors.ACCENT_DIM}; padding: 5px 12px; font-size: 10px; font-weight: bold; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.28); }}
        """)
        save_btn.clicked.connect(self._flush_and_close)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    # ─── Drag (title bar) ───

    def has_custom_position(self) -> bool:
        """Mirrors Compass/MiniMap's own has_custom_position() — once the
        user has dragged this panel, panel_layout_engine.py stops
        re-centering it on every resize/reposition and just keeps the
        dragged spot on-screen instead."""
        return self._custom_pos is not None

    def _on_header_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_global = event.globalPosition().toPoint()

    def _on_header_move(self, event):
        if self._drag_last_global is None:
            return
        pos = event.globalPosition().toPoint()
        delta = pos - self._drag_last_global
        self._drag_last_global = pos
        if delta.x() or delta.y():
            self.move(self.pos() + delta)
            self._custom_pos = self.pos()

    def _on_header_release(self, event):
        self._drag_last_global = None

    # ─── Palette selection ───

    def _on_effect_selected(self, key: str):
        """Picks the paint brush AND loads that effect's params into
        _EffectConfigBlock — clicking a card is "clicking the effect", and
        its params show right away below the palette regardless of
        whether anything's painted yet (see _EffectConfigBlock's own
        docstring). CAMADAS (right column) is a separate, simpler list of
        only what's actually painted — not touched here."""
        self.grid.set_brush(key)
        self._current_brush_key = key
        self._erase_btn.setChecked(False)
        for k, card in self._effect_cards.items():
            card.set_selected(k == key)
        self._config_block.load(key, _effect_icon(key), effect_label(key), self.grid.layers[key])

    def _on_eraser_selected(self):
        self.grid.set_brush("")
        for card in self._effect_cards.values():
            card.set_selected(False)
        self._erase_btn.setChecked(True)

    def _on_search_changed(self, text: str):
        """Filters cards (and hides a category entirely once none of its
        cards match) by substring on the effect's name — same idea as
        every other "🔍 Buscar..." filter box elsewhere in the app."""
        query = text.strip().lower()
        for cat_lbl, cat_row in self._category_sections:
            any_visible = False
            for i in range(cat_row.count() - 1):  # last item is the trailing stretch
                item = cat_row.itemAt(i)
                widget = item.widget()
                if widget is None:
                    continue
                match = not query or query in effect_label(widget.key).lower()
                widget.setVisible(match)
                any_visible = any_visible or match
            cat_lbl.setVisible(any_visible)

    # ─── CAMADAS list (glance-only — editing lives in _EffectConfigBlock) ───

    def _refresh_layers_list(self):
        """Rebuilds CAMADAS from self.grid.layers — only effects that
        currently have at least one painted cell get a row, same "appears
        once you actually use it" spirit as the shoreline overlay only
        attaching once an asset has any effect at all. Only called on
        structural changes (a cell got painted/erased, or a new asset
        loaded) — never from a config-block slider tick, which only
        touches self.grid.layers' values, not which effects are painted."""
        while self._layers_list.count():
            item = self._layers_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._layer_rows = {}

        active = [(key, icon, label) for key, icon, label in ASSET_EFFECT_TYPES
                  if any(self.grid.layers[key]["cells"])]
        if not active:
            self._layers_list.addWidget(self._layers_empty_lbl)
            self._layers_empty_lbl.show()
            return
        for key, icon, label in active:
            row = _LayerRow(key, icon, label)
            row.clicked.connect(self._on_effect_selected)
            row.clear_requested.connect(self._on_layer_clear_requested)
            self._layers_list.addWidget(row)
            self._layer_rows[key] = row

    def _on_layer_clear_requested(self, key: str):
        self.grid.clear_layer(key)  # emits painted -> _on_layers_mutated

    # ─── Config block (Cor/Intensidade/Raio/Brilho for the selected card) ───

    def _on_config_changed(self):
        self._config_block.apply_to(self.grid.layers[self._config_block.key])
        self.grid.update()
        self._schedule_autosave()

    def _on_config_clear(self):
        self.grid.clear_layer(self._config_block.key)  # emits painted -> _on_layers_mutated

    # ─── Shared refresh / autosave / close / sizing ───

    def _on_layers_mutated(self):
        """Single entry point for "a cell got painted/erased". A drag
        stroke fires this on every mouse-move, many times a second — most
        of those only add/remove cells WITHIN an effect that's already
        listed in CAMADAS, which changes nothing about that row's own
        widgets, so rebuilding the whole list (and the app-wide resize/
        reposition that follows a row appearing/disappearing) on every one
        of them stalls the UI thread mid-stroke for no reason — enough to
        make Windows show its own "not responding" ghost window over the
        app. Only rebuild when the SET of painted effects itself changed
        (a row's first cell just got painted, or its last one just got
        erased) — the actual rare case that needs a new/removed row."""
        self.grid.update()
        active_keys = {key for key, _icon, _label in ASSET_EFFECT_TYPES if any(self.grid.layers[key]["cells"])}
        if active_keys != set(self._layer_rows.keys()):
            self._refresh_layers_list()
            self._resize_to_content()
        self._schedule_autosave()

    def _resize_to_content(self):
        """This panel has no fixed height (see __init__) — ask MainLayout
        to re-measure and reposition now that the content that drives
        PanelManager._content_height() just changed shape (a row
        appeared/disappeared, or one expanded/collapsed). MainLayout is
        this panel's direct Qt parent (see AssetEffectsPanel(self._l) in
        the mediator) — NOT self.window(), which walks past MainLayout
        all the way up to the app's actual top-level QMainWindow (MainLayout
        itself lives inside AmbientBackground, not a window), which has no
        _reposition method, so that call was silently doing nothing."""
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, "_reposition"):
            parent._reposition()

    def _schedule_autosave(self):
        self._autosave_timer.start()

    def _flush_and_close(self):
        """Used by Salvar/Fechar/✕ alike — always saves (not just when a
        debounced autosave happens to be pending) before closing, so
        "Salvar" is a guaranteed apply-then-close, not a no-op when
        nothing's changed since the last autosave tick."""
        self._on_save()
        self.close_requested.emit()

    # ─── Public API ───

    def load_asset(self, asset_id: str, asset_name: str, thumbnail: QPixmap | None, layers: dict[str, dict],
                    is_water: bool = False, shore_foam: bool = True):
        # Flush any pending autosave from whatever asset was loaded before
        # — without this, a debounced save could fire after asset_id has
        # already moved on to the new asset and silently save the OLD
        # grid contents under the NEW asset's id.
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
            self._on_save()
        self.asset_id = asset_id
        self._title.setText(f"✨ Efeitos — {asset_name or asset_id}")
        self.grid.set_thumbnail(thumbnail)
        self.grid.load(layers)
        self._refresh_layers_list()
        self._on_effect_selected("emissivo")
        self._foam_row.setVisible(is_water)
        self._foam_check.blockSignals(True)
        self._foam_check.setChecked(shore_foam)
        self._foam_check.blockSignals(False)

    def _on_foam_toggled(self, checked: bool):
        if self.asset_id:
            self.foam_toggled.emit(self.asset_id, checked)

    def _on_save(self):
        self._autosave_timer.stop()
        self.saved.emit(self.asset_id, self.grid.layers)

    def paintEvent(self, event):
        paint_glass_panel(self)
