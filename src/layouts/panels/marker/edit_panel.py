"""MarkerEditPanel — "rides" in the same PanelManager slot as
MarkerToolPanel (never visible at the same time — see MarkerMediator),
shown when an existing MarkerItem is selected. Header + GERAL/VISIBILIDADE
tabs (EditorTabBar, reused from the Items/Habilidades editors)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
    QLineEdit, QComboBox, QStackedWidget, QWidget, QMenu,
)
from PySide6.QtGui import QAction, QColor
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Typography, menu_qss
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.items.editor_base import EditorTabBar, SquareCheck
from src.layouts.panels.marker.icon_picker import IconPicker
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare
from src.engines.marker import (
    CATEGORIES, EFFECTS, ICONS, INTENSITY_MAX, INTENSITY_MIN, OPACITY_MAX, OPACITY_MIN,
    RADIUS_MAX, RADIUS_MIN, category_label, normalize_effect_layers,
)

# Small glyph per shader effect — cosmetic only, keeps _MarkerEffectBlock's
# header from being just plain text (EFFECTS itself has no icon column,
# unlike CATEGORIES/ASSET_EFFECT_TYPES, since the menu button never needed
# one before this per-effect block existed).
_EFFECT_ICONS = {
    "redemoinhos": "🌀", "folhas": "🍃", "nuvens": "☁", "espinhos": "🌵", "brilho": "✨",
}


def _no_wheel(widget):
    """Ignores mouse-wheel events on `widget` instead of letting it bump
    the current value — this panel's own scroll (or a parent panel's, once
    the content grows past the visible height) used to silently change
    whatever combo/spin box the cursor happened to be over mid-scroll,
    Categoria included. Overriding the instance's own wheelEvent (rather
    than an installed event filter) keeps Qt's normal ignored-event
    propagation: whatever scroll area is underneath still receives the
    wheel event and scrolls normally, exactly as if the cursor were over a
    plain label."""
    widget.wheelEvent = lambda event: event.ignore()
    return widget


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
        font-weight: {Typography.WEIGHT_MEDIUM}; background: transparent; border: none;
    """)
    return lbl


def _field_row(label: str, widget: QWidget) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(3)
    col.addWidget(_field_label(label))
    col.addWidget(widget)
    return col


def _line_edit() -> QLineEdit:
    w = QLineEdit()
    w.setFixedHeight(26)
    w.setStyleSheet(f"""
        QLineEdit {{
            background: rgba(10, 16, 30, 0.7); border: 1px solid {Colors.BORDER_SUBTLE};
            border-radius: 4px; padding: 3px 8px; color: {Colors.TEXT_PRIMARY};
            font-size: {Typography.SIZE_XS}px;
        }}
        QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
    """)
    return w


class _InfoRow(QFrame):
    """Read-only label:value row — POSIÇÃO's X/Y/Z (no local DB access,
    just displaying whatever MarkerMediator hands over)."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(_field_label(label))
        self.value = QLabel("—")
        self.value.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_PRIMARY};
            background: transparent; border: none;
        """)
        layout.addWidget(self.value, 1)

    def set_value(self, text: str):
        self.value.setText(text)


class _MarkerEffectBlock(QFrame):
    """One active shader effect's own Intensidade/Raio/Opacidade/Cor — shown
    only while that effect is checked in the "Efeitos ao redor" menu (see
    MarkerEditPanel._refresh_effect_blocks). Each effect used to share one
    global intensity/radius with every other active effect; now each gets
    its own independent layer, same "camadas" spirit as AssetEffectsPanel's
    _EffectConfigBlock, just without blend mode/visibility (those live on
    the menu toggle itself here, there's no separate paintable region)."""

    changed = Signal(str, str, object)  # key, field ("intensity"/"radius"/"opacity"/"color"), value
    picker_toggled = Signal()  # inline color picker expanded/collapsed — panel needs re-sizing

    def __init__(self, key: str, label: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._color = "#FFFFFF"
        self._hsv = [0, 0, 100]
        self.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel(f"{_EFFECT_ICONS.get(key, '')} {label}")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;")
        header.addWidget(title, 1)
        self._swatch = QToolButton()
        self._swatch.setFixedSize(24, 18)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.setToolTip("Cor do efeito")
        self._swatch.clicked.connect(self._toggle_picker)
        header.addWidget(self._swatch)
        outer.addLayout(header)

        self._intensity = BrushSlider("Intensidade", "🌪", INTENSITY_MIN, INTENSITY_MAX, INTENSITY_MIN, "%")
        self._intensity.value_changed.connect(lambda v: self.changed.emit(self.key, "intensity", v))
        outer.addWidget(self._intensity)

        self._radius = BrushSlider("Raio", "📏", RADIUS_MIN, RADIUS_MAX, RADIUS_MIN, "m")
        self._radius.value_changed.connect(lambda v: self.changed.emit(self.key, "radius", v))
        outer.addWidget(self._radius)

        self._opacity = BrushSlider("Opacidade", "◐", OPACITY_MIN, OPACITY_MAX, OPACITY_MAX, "%")
        self._opacity.value_changed.connect(lambda v: self.changed.emit(self.key, "opacity", v))
        outer.addWidget(self._opacity)

        self._picker_frame = QFrame()
        self._picker_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        picker_lay = QVBoxLayout(self._picker_frame)
        picker_lay.setContentsMargins(0, 4, 0, 0)
        picker_lay.setSpacing(4)
        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(12)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        picker_lay.addWidget(self._hue_bar)
        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(56)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        picker_lay.addWidget(self._sv_square)
        outer.addWidget(self._picker_frame)
        self._picker_frame.setVisible(False)

    def load(self, layer: dict):
        for w in (self._intensity, self._radius, self._opacity):
            w.blockSignals(True)
        self._intensity.set_value(layer["intensity"])
        self._radius.set_value(layer["radius"])
        self._opacity.set_value(layer["opacity"])
        for w in (self._intensity, self._radius, self._opacity):
            w.blockSignals(False)
        self._set_color(layer.get("color", "#FFFFFF"), emit=False)

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
        self._swatch.setStyleSheet(
            f"QToolButton {{ background: {self._color}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}"
        )
        if emit:
            self.changed.emit(self.key, "color", self._color)

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


class MarkerEditPanel(QFrame):
    PANEL_WIDTH = 300

    name_changed = Signal(str)
    category_changed = Signal(str)
    icon_changed = Signal(str)
    description_changed = Signal(str)
    effects_changed = Signal(list)
    effect_layer_changed = Signal(str, str, object)  # key, field, value
    shadow_enabled_changed = Signal(bool)
    shadow_strength_changed = Signal(float)
    close_requested = Signal()
    content_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(8)

        layout.addLayout(self._build_header())
        layout.addWidget(self._sep())

        self._tab_bar = EditorTabBar(["GERAL", "VISIBILIDADE"])
        layout.addWidget(self._tab_bar)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_geral_tab())
        self._stack.addWidget(self._build_visibilidade_tab())
        self._tab_bar.tab_changed.connect(self._stack.setCurrentIndex)
        layout.addWidget(self._stack)

    # ─── Header ───

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(10)

        self._header_icon = QLabel("📍")
        self._header_icon.setStyleSheet("font-size: 26px; background: transparent; border: none;")
        header.addWidget(self._header_icon)

        info = QVBoxLayout()
        info.setSpacing(0)
        self._header_category = QLabel("Ponto de Interesse")
        self._header_category.setStyleSheet(f"""
            font-size: {Typography.SIZE_MD}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        info.addWidget(self._header_category)
        subtitle = QLabel("Marcador")
        subtitle.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)
        info.addWidget(subtitle)
        header.addLayout(info, 1)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        return header

    @staticmethod
    def _sep() -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    # ─── GERAL ───

    def _build_geral_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(10)

        self.name_edit = _line_edit()
        self.name_edit.textEdited.connect(lambda t: self._emit(self.name_changed, t))
        layout.addLayout(_field_row("Nome", self.name_edit))

        self.category_combo = QComboBox()
        _no_wheel(self.category_combo)
        self.category_combo.setFixedHeight(26)
        self.category_combo.setStyleSheet(f"""
            QComboBox {{
                background: rgba(10, 16, 30, 0.7); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 3px 8px; color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_XS}px;
            }}
            QComboBox:hover {{ border-color: {Colors.BORDER_HOVER}; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_ELEVATED}; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        for key, icon, label in CATEGORIES:
            self.category_combo.addItem(f"{icon} {label}", key)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        layout.addLayout(_field_row("Categoria", self.category_combo))

        self._icon_picker = IconPicker(ICONS, button_size=30, max_height=150)
        self._icon_picker.icon_picked.connect(lambda ic: self._emit(self.icon_changed, ic))
        icons_col = QVBoxLayout()
        icons_col.setSpacing(3)
        icons_col.addWidget(_field_label("Ícone"))
        icons_col.addWidget(self._icon_picker)
        layout.addLayout(icons_col)

        self.description_edit = _line_edit()
        self.description_edit.textEdited.connect(lambda t: self._emit(self.description_changed, t))
        layout.addLayout(_field_row("Descrição", self.description_edit))

        layout.addStretch()
        return page

    def _on_category_changed(self, index: int):
        if self._syncing:
            return
        key = self.category_combo.itemData(index)
        self.category_changed.emit(key)

    # ─── VISIBILIDADE ───

    def _build_visibilidade_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(10)

        layout.addWidget(_field_label("POSIÇÃO"))
        self.pos_x_row = _InfoRow("X")
        self.pos_y_row = _InfoRow("Y")
        self.pos_z_row = _InfoRow("Z")
        layout.addWidget(self.pos_x_row)
        layout.addWidget(self.pos_y_row)
        layout.addWidget(self.pos_z_row)
        layout.addWidget(self._sep())

        self.effects_btn = QToolButton()
        self.effects_btn.setText("Shaders: Nenhum")
        self.effects_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.effects_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.effects_btn.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                color: {Colors.TEXT_PRIMARY}; background: rgba(255,255,255,0.04);
                padding: 5px 8px; font-size: {Typography.SIZE_XS}px; text-align: left;
            }}
            QToolButton:hover {{ border-color: {Colors.BORDER_HOVER}; }}
            QToolButton::menu-indicator {{ image: none; width: 0; }}
        """)
        self._effects_menu = QMenu(self.effects_btn)
        self._effects_menu.setStyleSheet(menu_qss())
        self._effect_actions: dict[str, QAction] = {}
        for key, label in EFFECTS:
            action = QAction(label, self._effects_menu)
            action.setCheckable(True)
            action.toggled.connect(lambda _c, k=key: self._on_effect_toggled(k))
            self._effects_menu.addAction(action)
            self._effect_actions[key] = action
        self.effects_btn.setMenu(self._effects_menu)
        layout.addLayout(_field_row("Efeitos ao redor", self.effects_btn))

        # One block per currently-active effect (see _refresh_effect_blocks)
        # — each with its own Intensidade/Raio/Opacidade/Cor now, instead of
        # one slider+spin shared by every active effect.
        self._effect_blocks_layout = QVBoxLayout()
        self._effect_blocks_layout.setSpacing(6)
        layout.addLayout(self._effect_blocks_layout)
        self._effect_blocks: dict[str, _MarkerEffectBlock] = {}

        layout.addWidget(self._sep())

        self.shadow_check = SquareCheck(checked=False)
        self.shadow_check.toggled.connect(lambda c: self._emit(self.shadow_enabled_changed, c))
        shadow_row = QHBoxLayout()
        shadow_row.setSpacing(8)
        shadow_row.addWidget(_field_label("Sombra de Contato"))
        shadow_row.addStretch()
        shadow_row.addWidget(self.shadow_check)
        layout.addLayout(shadow_row)

        self.shadow_strength_slider = BrushSlider("Força", "◑", 0, 100, 50, "%")
        self.shadow_strength_slider.value_changed.connect(
            lambda v: self._emit(self.shadow_strength_changed, v)
        )
        layout.addWidget(self.shadow_strength_slider)

        layout.addStretch()
        return page

    def _on_effect_toggled(self, _key: str):
        if self._syncing:
            return
        active = [k for k, action in self._effect_actions.items() if action.isChecked()]
        self._update_effects_label(active)
        self._refresh_effect_blocks(active)
        self.effects_changed.emit(active)

    def _refresh_effect_blocks(self, active: list[str]):
        """Adds/removes _MarkerEffectBlock rows to match `active` — called
        both from the menu toggle handler and from set_data(). Blocks for
        effects that are still active keep their widget instance (and
        whatever popup state), only the newly (de)activated ones change."""
        for key in list(self._effect_blocks):
            if key not in active:
                block = self._effect_blocks.pop(key)
                self._effect_blocks_layout.removeWidget(block)
                block.setParent(None)
        label_by_key = dict(EFFECTS)
        for key in active:
            if key in self._effect_blocks:
                continue
            block = _MarkerEffectBlock(key, label_by_key.get(key, key))
            block.changed.connect(self._on_effect_layer_changed)
            block.picker_toggled.connect(self.content_changed.emit)
            self._effect_blocks_layout.addWidget(block)
            self._effect_blocks[key] = block

    def _on_effect_layer_changed(self, key: str, field: str, value):
        if not self._syncing:
            self.effect_layer_changed.emit(key, field, value)

    def _update_effects_label(self, active: list[str]):
        if not active:
            self.effects_btn.setText("Shaders: Nenhum")
            return
        first_label = dict(EFFECTS).get(active[0], active[0])
        extra = f" +{len(active) - 1}" if len(active) > 1 else ""
        self.effects_btn.setText(f"Shaders: {first_label}{extra}")

    # ─── Public API ───

    def _emit(self, signal, value):
        if not self._syncing:
            signal.emit(value)

    def set_data(self, props, pos_x: float, pos_y: float, z: float):
        self._syncing = True
        self._header_icon.setText(props.icon)
        self._header_category.setText(category_label(props.category))
        self.name_edit.setText(props.name)
        idx = self.category_combo.findData(props.category)
        self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._icon_picker.set_checked(props.icon)
        self.description_edit.setText(props.description)
        self.pos_x_row.set_value(f"{pos_x:.0f}")
        self.pos_y_row.set_value(f"{pos_y:.0f}")
        self.pos_z_row.set_value(f"{z:.0f}")
        for key, action in self._effect_actions.items():
            action.setChecked(key in props.effects)
        self._update_effects_label(list(props.effects))
        self._refresh_effect_blocks(list(props.effects))
        layers = normalize_effect_layers(props.effect_layers, props.effects, props.effect_radius, props.effect_intensity)
        for key, block in self._effect_blocks.items():
            block.load(layers[key])
        self.shadow_check.setChecked(props.shadow_enabled)
        self.shadow_strength_slider.set_value(props.shadow_strength)
        self._syncing = False

    def update_header(self, icon: str, category: str):
        """Lightweight header-only refresh — used by MarkerMediator after a
        live icon/category edit, instead of a full set_data() (which would
        reset cursor position/scroll on every keystroke elsewhere)."""
        self._header_icon.setText(icon)
        self._header_category.setText(category_label(category))

    def paintEvent(self, event):
        paint_glass_panel(self)
