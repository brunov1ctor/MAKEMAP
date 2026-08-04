"""SkyEditPanel — opened when "Sky Light" is picked in LightPanel. Unlike
every other light type, "sky" isn't a placeable object (see GLOBAL_TYPES in
src/engines/light.py): there's exactly one sky setting per map, and this
panel controls it directly instead of arming a placement tool. Shares the
same PanelManager dock slot as LightPanel/LightEditPanel (see
LightMediator._on_type_picked)."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QSizePolicy
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Typography
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.brush.slider import BrushSlider
from src.layouts.panels.light.edit_panel import _ColorField

# Common night-sky tints — one click instead of hunting the HSV picker for
# a color you already know you want (see _ColorField's ↺ revert button for
# getting back a color you overwrote by accident).
_NIGHT_PRESETS = [
    "#0B1533",  # padrão do app (default_color("sky"))
    "#0D2B45",  # azul petróleo
    "#1B1035",  # roxo profundo
    "#2C2C54",  # índigo
    "#3A2E52",  # dusk acinzentado
    "#000000",  # preto absoluto
]


class SkyEditPanel(QFrame):
    PANEL_WIDTH = 280

    day_amount_changed = Signal(float)
    color_changed = Signal(str)
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
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("🌌 CÉU")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
        header.addStretch()
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
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)
        layout.addWidget(self._sep())

        hint = QLabel("Ilumina o mapa inteiro — não é um objeto posicionado")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10pt; background: transparent; border: none;")
        layout.addWidget(hint)

        # 100 = dia cheio (mapa como sempre foi, sem escurecer nada), 0 =
        # noite cheia (tinta de "Cor da noite" aplicada por cima do mapa
        # inteiro — luzes colocadas continuam somando brilho por cima dela).
        self.day_amount_slider = BrushSlider("Dia/Noite", "🌗", 0, 100, 100, "%")
        self.day_amount_slider.value_changed.connect(lambda v: self._emit(self.day_amount_changed, v))
        layout.addWidget(self.day_amount_slider)

        self.color_field = _ColorField("Cor da noite", presets=_NIGHT_PRESETS)
        self.color_field.color_changed.connect(lambda c: self._emit(self.color_changed, c))
        self.color_field.toggled.connect(self.content_changed.emit)
        layout.addWidget(self.color_field)

    @staticmethod
    def _sep() -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _emit(self, signal, value):
        if not self._syncing:
            signal.emit(value)

    def set_data(self, props):
        self._syncing = True
        self.day_amount_slider.set_value(props.day_amount)
        self.color_field.set_color(props.color)
        self._syncing = False

    def paintEvent(self, event):
        paint_glass_panel(self)
