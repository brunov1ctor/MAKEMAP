"""4. Inspector + 4.1 Quest + 4.2 Layers — 3 painéis independentes colapsáveis."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QTabWidget, QWidget, QScrollArea, QSizePolicy, QSlider,
    QLineEdit, QComboBox, QCheckBox, QSpinBox,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors, Metrics, Typography
from src.components.collapsible_panel import CollapsiblePanel


# ─── Styles ────────────────────────────────────────────────────────────────

_FIELD_STYLE = f"""
    background: rgba(10, 16, 30, 0.7);
    border: 1px solid {Colors.BORDER_SUBTLE};
    border-radius: 4px;
    padding: 3px 8px;
    color: {Colors.TEXT_PRIMARY};
    font-size: {Typography.SIZE_XS}px;
"""

_FIELD_FOCUS = f"""
    border-color: {Colors.ACCENT};
    background: rgba(10, 16, 30, 0.85);
"""

_LABEL_STYLE = f"""
    font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
    font-weight: {Typography.WEIGHT_MEDIUM}; background: transparent; border: none;
"""


# ─── Form Fields ───────────────────────────────────────────────────────────

class _FieldRow(QFrame):
    def __init__(self, label: str, widget: QWidget, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFixedWidth(72)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)
        layout.addWidget(widget, 1)


def _text_field(placeholder=""):
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setFixedHeight(24)
    w.setStyleSheet(f"QLineEdit {{ {_FIELD_STYLE} }} QLineEdit:focus {{ {_FIELD_FOCUS} }}")
    return w


def _combo_field(items):
    w = QComboBox()
    w.addItems(items)
    w.setFixedHeight(24)
    w.setStyleSheet(f"""
        QComboBox {{ {_FIELD_STYLE} }}
        QComboBox:hover {{ border-color: {Colors.BORDER_HOVER}; }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox QAbstractItemView {{
            background: rgba(20, 32, 55, 0.95);
            border: 1px solid {Colors.BORDER};
            color: {Colors.TEXT_PRIMARY};
        }}
    """)
    return w


def _spin_field(min_v=0, max_v=100, value=1):
    w = QSpinBox()
    w.setRange(min_v, max_v)
    w.setValue(value)
    w.setFixedHeight(24)
    w.setStyleSheet(f"""
        QSpinBox {{ {_FIELD_STYLE} }}
        QSpinBox:focus {{ {_FIELD_FOCUS} }}
        QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; }}
    """)
    return w


def _check_field(checked=False):
    w = QCheckBox()
    w.setChecked(checked)
    w.setStyleSheet(f"""
        QCheckBox {{ background: transparent; border: none; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px; border-radius: 4px;
            border: 1px solid {Colors.BORDER};
            background: rgba(10, 16, 30, 0.7);
        }}
        QCheckBox::indicator:checked {{
            background: {Colors.ACCENT};
            border-color: {Colors.ACCENT};
        }}
    """)
    return w


# ─── 4. Inspector Panel ───────────────────────────────────────────────────

class InspectorPanel(CollapsiblePanel):
    """4. Inspector — header + abas com formulários (colapsável)."""

    def __init__(self, parent=None):
        super().__init__(title="Inspector", icon="🔍", parent=parent, radius=14)

        # Título maior
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)

        # Header do elemento
        self.header = _ElementHeader()
        self.content_layout.addWidget(self.header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar::tab {{
                background: transparent; color: {Colors.TEXT_MUTED};
                padding: 7px 10px; font-size: {Typography.SIZE_XS}px;
                font-weight: {Typography.WEIGHT_BOLD};
                border: none; border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{ color: {Colors.ACCENT}; border-bottom-color: {Colors.ACCENT}; }}
            QTabBar::tab:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        self.tabs.addTab(_build_tab_geral(), "GERAL")
        self.tabs.addTab(_build_tab_stats(), "STATS")
        self.tabs.addTab(_build_tab_drops(), "DROPS")
        self.tabs.addTab(_build_tab_ia(), "IA")
        self.tabs.addTab(_build_tab_outros(), "OUTROS")
        self.content_layout.addWidget(self.tabs, 1)

    def set_element(self, **kwargs):
        self.header.set_element(**kwargs)


# ─── 4.1 Quest Panel ──────────────────────────────────────────────────────

class QuestPanel(CollapsiblePanel):
    """4.1 Quest Relacionada — painel colapsável."""

    def __init__(self, parent=None):
        super().__init__(title="Quest Relacionada", icon="📜", parent=parent, radius=10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        # Status badge no header
        self.status_badge = QLabel("Ativa")
        self.status_badge.setStyleSheet(f"""
            font-size: 8px; color: {Colors.SUCCESS};
            background: rgba(102, 187, 106, 0.15);
            border-radius: 6px; padding: 2px 6px; border: none;
        """)
        header_layout = self._main_layout.itemAt(0).layout()
        header_layout.insertWidget(header_layout.count() - 1, self.status_badge)

        # Name
        self.quest_name = QLabel("Protegendo a Vila")
        self.quest_name.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        self.content_layout.addWidget(self.quest_name)

        # Details
        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)
        self.quest_type = QLabel("Quest Principal")
        self.quest_type.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)
        self.quest_level = QLabel("Nível 10")
        self.quest_level.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.ACCENT};
            font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;
        """)
        detail_row.addWidget(self.quest_type)
        detail_row.addWidget(self.quest_level)
        detail_row.addStretch()
        self.content_layout.addLayout(detail_row)

    def set_quest(self, name="", level="", type_="", status=""):
        self.quest_name.setText(name or "—")
        self.quest_level.setText(f"Nível {level}" if level else "")
        self.quest_type.setText(type_)
        self.status_badge.setText(status or "Ativa")


# ─── 4.2 Layers Panel ─────────────────────────────────────────────────────

class _LayerItem(QFrame):
    def __init__(self, icon, name, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            _LayerItem {{ background: transparent; border: none; border-radius: 4px; }}
            _LayerItem:hover {{ background: {Colors.PANEL_HOVER}; }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(3)

        drag = QLabel("☰")
        drag.setFixedWidth(12)
        drag.setStyleSheet(f"font-size: 8px; color: {Colors.TEXT_DISABLED}; background: transparent; border: none;")
        drag.setCursor(Qt.CursorShape.SizeAllCursor)
        layout.addWidget(drag)

        vis = QToolButton()
        vis.setText("👁")
        vis.setFixedSize(16, 16)
        vis.setCheckable(True)
        vis.setChecked(True)
        vis.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 9px; color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:checked {{ color: {Colors.ACCENT}; }}
        """)
        layout.addWidget(vis)

        lock = QToolButton()
        lock.setText("🔓")
        lock.setFixedSize(16, 16)
        lock.setCheckable(True)
        lock.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 9px; color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:checked {{ color: {Colors.WARNING}; }}
        """)
        layout.addWidget(lock)

        lbl = QLabel(f"{icon} {name}")
        lbl.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_SECONDARY};
            background: transparent; border: none;
        """)
        layout.addWidget(lbl, 1)

        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(0, 100)
        opacity.setValue(100)
        opacity.setFixedWidth(36)
        opacity.setFixedHeight(10)
        opacity.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: {Colors.BG_TERTIARY}; height: 2px; border-radius: 1px; }}
            QSlider::handle:horizontal {{ background: {Colors.ACCENT}; width: 6px; height: 6px; margin: -2px 0; border-radius: 3px; }}
        """)
        layout.addWidget(opacity)


class LayersPanel(CollapsiblePanel):
    """4.2 Camadas Ativas — painel colapsável."""

    def __init__(self, parent=None):
        super().__init__(title="Camadas Ativas", icon="📐", parent=parent, radius=10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        # Título um pouco maior
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)

        # Botão + no header
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setFixedSize(18, 18)
        add_btn.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 11px; color: {Colors.ACCENT}; background: transparent; border-radius: 4px; }}
            QToolButton:hover {{ background: {Colors.ACCENT_DIM}; }}
        """)
        header_layout = self._main_layout.itemAt(0).layout()
        header_layout.insertWidget(header_layout.count() - 1, add_btn)

        # Layers
        layers = [
            ("🎨", "Terreno"), ("🌿", "Biomas"), ("👹", "Mobs"),
            ("🧙", "NPCs"), ("📜", "Quests"), ("🏰", "Dungeons"),
            ("💀", "Bosses"), ("💎", "Recursos"), ("🛤", "Estradas"),
            ("🏴", "Áreas PvP"),
        ]
        for icon, name in layers:
            self.content_layout.addWidget(_LayerItem(icon, name))


# ─── Element Header (internal) ─────────────────────────────────────────────

class _ElementHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(90)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Image
        self.image = QFrame()
        self.image.setFixedSize(68, 68)
        self.image.setStyleSheet(f"""
            QFrame {{
                background: rgba(10, 16, 30, 0.7);
                border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 12px;
            }}
        """)
        self._icon = QLabel("👹", self.image)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setGeometry(0, 0, 68, 68)
        self._icon.setStyleSheet("font-size: 28px; background: transparent; border: none;")
        layout.addWidget(self.image)

        # Info
        info = QVBoxLayout()
        info.setSpacing(2)

        self.name_label = QLabel("Goblin Guerreiro")
        self.name_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_LG}px; font-weight: {Typography.WEIGHT_BLACK};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        info.addWidget(self.name_label)

        self.type_label = QLabel("Mob • Elite")
        self.type_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)
        info.addWidget(self.type_label)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        self.level_label = QLabel("⚔ Nível 10")
        self.level_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.ACCENT};
            font-weight: {Typography.WEIGHT_BOLD};
            background: {Colors.ACCENT_DIM}; border-radius: 8px;
            padding: 2px 8px; border: none;
        """)
        badges.addWidget(self.level_label)

        self.tags_label = QLabel("mob, guerreiro, floresta")
        self.tags_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_MUTED};
            background: transparent; border: none;
        """)
        badges.addWidget(self.tags_label)
        badges.addStretch()
        info.addLayout(badges)
        info.addStretch()
        layout.addLayout(info, 1)

    def set_element(self, name="", type_="", level="", tags="", icon="👹"):
        self.name_label.setText(name or "Nenhum elemento")
        self.type_label.setText(type_ or "Selecione algo no mapa")
        self._icon.setText(icon)
        if level:
            self.level_label.setText(f"⚔ Nível {level}")
            self.level_label.show()
        else:
            self.level_label.hide()
        self.tags_label.setText(tags)


# ─── Tab Builders ──────────────────────────────────────────────────────────

def _build_tab_geral():
    page = QWidget()
    page.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(4, 8, 4, 4)
    layout.setSpacing(4)
    layout.addWidget(_FieldRow("Facção", _combo_field(["Neutro", "Aliado", "Hostil"])))
    layout.addWidget(_FieldRow("Tipo", _combo_field(["Normal", "Elite", "Raro", "Boss"])))
    layout.addWidget(_FieldRow("Nível", _spin_field(1, 100, 10)))
    layout.addWidget(_FieldRow("Região", _combo_field(["Floresta do Amanhecer", "Vale do Eco"])))
    layout.addWidget(_FieldRow("Spawn", _text_field("X: 0, Y: 0")))
    layout.addWidget(_FieldRow("Respawn", _spin_field(0, 3600, 30)))
    layout.addWidget(_FieldRow("Raio", _spin_field(0, 500, 50)))
    layout.addWidget(_FieldRow("Patrulha", _check_field(True)))
    layout.addWidget(_FieldRow("Ativo", _check_field(True)))
    layout.addStretch()
    return page


def _build_tab_stats():
    page = QWidget()
    page.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(4, 8, 4, 4)
    layout.setSpacing(4)
    layout.addWidget(_FieldRow("HP", _spin_field(1, 999999, 450)))
    layout.addWidget(_FieldRow("MP", _spin_field(0, 99999, 120)))
    layout.addWidget(_FieldRow("ATK", _spin_field(0, 9999, 85)))
    layout.addWidget(_FieldRow("DEF", _spin_field(0, 9999, 40)))
    layout.addWidget(_FieldRow("SPD", _spin_field(0, 999, 12)))
    layout.addWidget(_FieldRow("Resistências", _text_field("Fogo: 10%, Gelo: 0%")))
    layout.addStretch()
    return page


def _build_tab_drops():
    page = QWidget()
    page.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(4, 8, 4, 4)
    layout.setSpacing(4)
    layout.addWidget(_FieldRow("Item", _combo_field(["Espada de Ferro", "Poção HP", "Ouro"])))
    layout.addWidget(_FieldRow("Chance", _spin_field(1, 100, 25)))
    layout.addWidget(_FieldRow("Quantidade", _spin_field(1, 99, 1)))
    layout.addWidget(_FieldRow("Condição", _combo_field(["Sempre", "Primeira Kill", "Quest Ativa"])))
    layout.addStretch()
    return page


def _build_tab_ia():
    page = QWidget()
    page.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(4, 8, 4, 4)
    layout.setSpacing(4)
    layout.addWidget(_FieldRow("Comportamento", _combo_field(["Passivo", "Agressivo", "Territorial"])))
    layout.addWidget(_FieldRow("Agressividade", _spin_field(0, 100, 70)))
    layout.addWidget(_FieldRow("Rota", _combo_field(["Circular", "Ping-Pong", "Aleatória"])))
    layout.addWidget(_FieldRow("Trigger", _combo_field(["Proximidade", "Ataque", "Quest"])))
    layout.addStretch()
    return page


def _build_tab_outros():
    page = QWidget()
    page.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(4, 8, 4, 4)
    layout.setSpacing(4)
    layout.addWidget(_FieldRow("Notas", _text_field("Anotações...")))
    layout.addWidget(_FieldRow("Tags", _text_field("mob, guerreiro")))
    layout.addWidget(_FieldRow("Referências", _text_field("quest_001")))
    layout.addStretch()
    return page
