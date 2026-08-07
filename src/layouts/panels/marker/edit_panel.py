"""MarkerEditPanel — "rides" in the same PanelManager slot as
MarkerToolPanel (never visible at the same time — see MarkerMediator),
shown when an existing MarkerItem is selected. Header + GERAL/VISIBILIDADE/
LINKS tabs (EditorTabBar, reused from the Items/Habilidades editors)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
    QLineEdit, QComboBox, QStackedWidget, QWidget, QDoubleSpinBox, QMenu,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Typography, menu_qss
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.items.editor_base import EditorTabBar
from src.layouts.panels.marker.icon_picker import IconPicker
from src.layouts.panels.brush.slider import BrushSlider
from src.engines.marker import CATEGORIES, EFFECTS, ICONS, category_label


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


class MarkerEditPanel(QFrame):
    PANEL_WIDTH = 300

    name_changed = Signal(str)
    category_changed = Signal(str)
    icon_changed = Signal(str)
    description_changed = Signal(str)
    effects_changed = Signal(list)
    radius_changed = Signal(float)
    effect_intensity_changed = Signal(float)
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

        self._tab_bar = EditorTabBar(["GERAL", "VISIBILIDADE", "LINKS"])
        layout.addWidget(self._tab_bar)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_geral_tab())
        self._stack.addWidget(self._build_visibilidade_tab())
        self._stack.addWidget(self._build_links_tab())
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

        self.effect_intensity_slider = BrushSlider("Intensidade", "🌪", 0, 100, 50, "%")
        self.effect_intensity_slider.value_changed.connect(
            lambda v: self._emit(self.effect_intensity_changed, v)
        )
        layout.addWidget(self.effect_intensity_slider)

        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0, 2000)
        self.radius_spin.setSuffix(" m")
        self.radius_spin.setValue(100)
        self.radius_spin.setFixedHeight(26)
        self.radius_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                background: rgba(10, 16, 30, 0.7); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 3px 8px; color: {Colors.TEXT_PRIMARY};
                font-size: {Typography.SIZE_XS}px;
            }}
            QDoubleSpinBox:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self.radius_spin.valueChanged.connect(lambda v: self._emit(self.radius_changed, v))
        layout.addLayout(_field_row("Raio", self.radius_spin))

        layout.addStretch()
        return page

    def _on_effect_toggled(self, _key: str):
        if self._syncing:
            return
        active = [k for k, action in self._effect_actions.items() if action.isChecked()]
        self._update_effects_label(active)
        self.effects_changed.emit(active)

    def _update_effects_label(self, active: list[str]):
        if not active:
            self.effects_btn.setText("Shaders: Nenhum")
            return
        first_label = dict(EFFECTS).get(active[0], active[0])
        extra = f" +{len(active) - 1}" if len(active) > 1 else ""
        self.effects_btn.setText(f"Shaders: {first_label}{extra}")

    # ─── LINKS ───

    def _build_links_tab(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 8, 4, 4)
        note = QLabel("Nenhum link conectado ainda.")
        note.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)
        layout.addWidget(note)
        layout.addStretch()
        return page

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
        self.effect_intensity_slider.set_value(props.effect_intensity)
        self.radius_spin.setValue(props.effect_radius)
        self._syncing = False

    def update_header(self, icon: str, category: str):
        """Lightweight header-only refresh — used by MarkerMediator after a
        live icon/category edit, instead of a full set_data() (which would
        reset cursor position/scroll on every keystroke elsewhere)."""
        self._header_icon.setText(icon)
        self._header_category.setText(category_label(category))

    def paintEvent(self, event):
        paint_glass_panel(self)
