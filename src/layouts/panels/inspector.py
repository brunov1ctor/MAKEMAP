"""4. Inspector + 4.2 Layers — painéis independentes colapsáveis."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QToolButton,
    QTabWidget, QWidget, QSizePolicy, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors, Typography
from src.components.collapsible_panel import CollapsiblePanel
from src.layouts.panels.mobs.categories import category_badge_color, category_label, category_tag_text_color
from src.layouts.panels.mobs.edit_widgets import _DropTile, _CatalogTile


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


_INFO_GRID_COLS = 2


class _InfoRow(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)
        self.value = QLabel("—")
        self.value.setWordWrap(True)
        self.value.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; color: {Colors.TEXT_PRIMARY};
            background: transparent; border: none;
        """)
        layout.addWidget(self.value)

    def set_value(self, value):
        text = "" if value is None else str(value)
        self.value.setText(text if text.strip() else "—")


class _InfoTab(QWidget):
    def __init__(self, spec: list[tuple[str, str, object]], parent=None):
        super().__init__(parent)
        self._spec = spec
        self.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 8, 4, 4)
        outer.setSpacing(4)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for col in range(_INFO_GRID_COLS):
            grid.setColumnStretch(col, 1)
        self._rows: dict[str, _InfoRow] = {}
        for i, (label, key, _fmt) in enumerate(spec):
            row = _InfoRow(label)
            self._rows[key] = row
            grid.addWidget(row, i // _INFO_GRID_COLS, i % _INFO_GRID_COLS)
        outer.addLayout(grid)
        outer.addStretch()

    def set_data(self, mob: dict | None):
        for label, key, fmt in self._spec:
            row = self._rows[key]
            if mob is None:
                row.set_value(None)
                continue
            raw = mob.get(key)
            row.set_value(fmt(raw, mob) if fmt else raw)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
        color: {Colors.TEXT_MUTED}; background: transparent; border: none;
    """)
    return lbl


_GRID_COLS = 5
_GRID_SPACING = 0
_MIN_TILE_SIZE = 20


def _tile_scroll_grid() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    scroll.setStyleSheet(f"""
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ width: 3px; background: transparent; }}
        QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 1px; min-height: 16px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    """)
    container = QWidget()
    rows = QVBoxLayout(container)
    rows.setContentsMargins(0, 0, 0, 0)
    rows.setSpacing(_GRID_SPACING)
    rows.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(container)
    return scroll, rows


def _row_tile_width(scroll: QScrollArea) -> int:
    avail = scroll.viewport().width() or scroll.width()
    tile_w = (avail - (_GRID_COLS - 1) * _GRID_SPACING) // _GRID_COLS
    return max(_MIN_TILE_SIZE, int(tile_w))


def _fill_grid(rows: QVBoxLayout, widgets: list[QWidget]):
    while rows.count():
        item = rows.takeAt(0)
        if item.layout():
            while item.layout().count():
                sub = item.layout().takeAt(0)
                if sub.widget():
                    sub.widget().deleteLater()
            item.layout().deleteLater()
    for start in range(0, len(widgets), _GRID_COLS):
        row = QHBoxLayout()
        row.setSpacing(_GRID_SPACING)
        for w in widgets[start:start + _GRID_COLS]:
            row.addWidget(w)
        row.addStretch()
        rows.addLayout(row)


class _GeralTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._info = _InfoTab(_GERAL_SPEC)
        layout.addWidget(self._info)

        layout.addWidget(_section_label("DROPS"))
        self._drops_empty_lbl = QLabel("Nenhum drop cadastrado.")
        self._drops_empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px; background: transparent; border: none;")
        layout.addWidget(self._drops_empty_lbl)
        self._drops_scroll, self._drops_grid = _tile_scroll_grid()
        self._drops_scroll.setMinimumHeight(70)
        layout.addWidget(self._drops_scroll, 1)

        layout.addWidget(_section_label("HABILIDADES"))
        self._abilities_empty_lbl = QLabel("Nenhuma habilidade cadastrada.")
        self._abilities_empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Typography.SIZE_XS}px; background: transparent; border: none;")
        layout.addWidget(self._abilities_empty_lbl)
        self._abilities_scroll, self._abilities_grid = _tile_scroll_grid()
        self._abilities_scroll.setMinimumHeight(70)
        layout.addWidget(self._abilities_scroll, 1)

    def set_data(self, mob: dict | None, drops: list[tuple[dict, float, int]] | None = None,
                 abilities: list[tuple[dict, bool]] | None = None):
        self._info.set_data(mob)
        drops = drops or []
        abilities = abilities or []
        self._drops_empty_lbl.setVisible(not drops)
        self._drops_scroll.setVisible(bool(drops))
        self._abilities_empty_lbl.setVisible(not abilities)
        self._abilities_scroll.setVisible(bool(abilities))
        QTimer.singleShot(0, lambda: self._fill_tiles(drops, abilities))

    def _fill_tiles(self, drops: list[tuple[dict, float, int]], abilities: list[tuple[dict, bool]]):
        drop_size = _row_tile_width(self._drops_scroll)
        _fill_grid(self._drops_grid, [
            _DropTile(item_dict, rate, qty, size=drop_size, removable=False)
            for item_dict, rate, qty in drops
        ])
        ability_size = max(_MIN_TILE_SIZE, _row_tile_width(self._abilities_scroll) - 16)
        _fill_grid(self._abilities_grid, [
            _CatalogTile(skill, size=ability_size) for skill, _unlinked in abilities
        ])


_GERAL_SPEC = [
    ("Nível", "level", None),
    ("Tipo", "tipo", None),
    ("Categoria", "category", None),
    ("Subcategoria", "subcategory", None),
    ("Região", "_zone_name", None),
    ("Ambiente", "ambiente", None),
    ("Elemento", "element", None),
    ("Descrição", "description", None),
]
_ATRIBUTOS_SPEC = [
    ("HP", "health", None),
    ("Mana", "mana", None),
    ("Ataque", "damage", None),
    ("Defesa", "defense", None),
    ("Velocidade", "velocidade", None),
    ("Precisão", "precisao", None),
    ("Esquiva", "esquiva", None),
    ("Crítico", "critico", None),
    ("Resist. Física", "resist_fisica", None),
    ("Resist. Mágica", "resist_magica", None),
    ("Tamanho", "tamanho", None),
    ("XP", "xp", None),
    ("Ouro", "ouro", None),
    ("Peso", "peso", None),
    ("Facção", "faction", None),
    ("Altura", "altura", None),
]
_IA_SPEC = [
    ("Tipo de IA", "ai_type", None),
    ("Comportamento", "comportamento", None),
    ("Alinhamento", "alinhamento", None),
]
_OUTROS_SPEC = [
    ("Respawn", "respawn_time", lambda v, m: f"{v}s" if v not in (None, "") else None),
    ("Raio Patrulha", "patrol_radius", None),
    ("Notas", "notes", None),
    ("Efeitos", "effect_notes", None),
    ("Animações", "animation_notes", None),
    ("Spawn", "spawn_notes", None),
]


# ─── 4. Inspector Panel ───────────────────────────────────────────────────

class InspectorPanel(CollapsiblePanel):
    def __init__(self, parent=None):
        super().__init__(title="Inspector", icon="🔍", parent=parent, radius=14)
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_SM}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        self.header = _ElementHeader()
        self.content_layout.addWidget(self.header)
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
        self._geral_tab = _GeralTab()
        self._atributos_tab = _InfoTab(_ATRIBUTOS_SPEC)
        self._ia_tab = _InfoTab(_IA_SPEC)
        self._outros_tab = _InfoTab(_OUTROS_SPEC)
        self.tabs.addTab(self._geral_tab, "GERAL")
        self.tabs.addTab(self._atributos_tab, "ATRIBUTOS")
        self.tabs.addTab(self._ia_tab, "IA")
        self.tabs.addTab(self._outros_tab, "OUTROS")
        self.content_layout.addWidget(self.tabs, 1)

    def set_element(self, **kwargs):
        self.header.set_element(**kwargs)
        self._clear_tabs()

    def set_mob(self, mob: dict, pixmap: QPixmap | None = None, region_name: str = "",
                drops: list[tuple[dict, float, int]] | None = None,
                abilities: list[tuple[dict, bool]] | None = None):
        self.header.set_element(
            name=mob.get("name", ""), type_=f"Mob • {mob.get('category', '')}".rstrip(" •"),
            level=str(mob.get("level") or ""), tags=mob.get("subcategory", ""),
            icon="👹", pixmap=pixmap, category=mob.get("category", ""),
        )
        data = dict(mob)
        data["_zone_name"] = region_name
        self._geral_tab.set_data(data, drops=drops, abilities=abilities)
        self._atributos_tab.set_data(data)
        self._ia_tab.set_data(data)
        self._outros_tab.set_data(data)

    def set_npc(self, npc: dict, pixmap: QPixmap | None = None, region_name: str = ""):
        self.header.set_element(
            name=npc.get("name", ""), type_=f"NPC • {npc.get('npc_type', '')}".rstrip(" •"),
            level=str(npc.get("level") or ""), tags=npc.get("subcategory", ""),
            icon="🧙", pixmap=pixmap, category=npc.get("category", ""),
        )
        data = dict(npc)
        data["_zone_name"] = region_name
        self._geral_tab.set_data(data, drops=[], abilities=[])
        self._atributos_tab.set_data(data)
        self._ia_tab.set_data(data)
        self._outros_tab.set_data(data)

    def clear(self):
        self.header.set_element()
        self._clear_tabs()

    def _clear_tabs(self):
        for tab in (self._geral_tab, self._atributos_tab, self._ia_tab, self._outros_tab):
            tab.set_data(None)


# ─── 4.2 Layers Panel ─────────────────────────────────────────────────────

# (item_types no canvas, label, ícone) — ordem de exibição
_LAYER_DEFS = [
    (["terrain"],     "Terreno",    "🎨"),
    (["zone"],        "Regiões",    "🗺"),
    (["effect"],      "Efeitos",    "✨"),
    (["river_path"],  "Rios",       "🌊"),
    (["road_path"],   "Estradas",   "🛤"),
    (["asset"],       "Assets",     "🖼"),
    (["mob_spawn"],   "Mobs",       "👹"),
    (["npc_spawn"],   "NPCs",       "🧙"),
    (["text"],        "Textos",     "📝"),
    (["light"],       "Luzes",      "💡"),
    (["marker"],      "Marcadores", "📍"),
]


class _LayerRow(QFrame):
    def __init__(self, icon: str, name: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self._vis_btn = QToolButton()
        self._vis_btn.setText("👁")
        self._vis_btn.setFixedSize(18, 18)
        self._vis_btn.setCheckable(True)
        self._vis_btn.setChecked(True)
        self._vis_btn.setStyleSheet(f"""
            QToolButton {{ border: none; font-size: 10px; color: {Colors.ACCENT}; background: transparent; }}
            QToolButton:!checked {{ color: {Colors.TEXT_DISABLED}; }}
        """)
        layout.addWidget(self._vis_btn)

        lbl = QLabel(f"{icon}  {name}")
        lbl.setStyleSheet(f"font-size: {Typography.SIZE_XXS}px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;")
        layout.addWidget(lbl, 1)

    def connect_toggle(self, callback):
        self._vis_btn.toggled.connect(callback)

    def set_visible_state(self, visible: bool):
        self._vis_btn.blockSignals(True)
        self._vis_btn.setChecked(visible)
        self._vis_btn.blockSignals(False)


class LayersPanel(CollapsiblePanel):
    """Camadas Ativas — aparece dinamicamente conforme tipos de itens
    são adicionados ao canvas; o olho controla a visibilidade global
    de cada categoria."""

    def __init__(self, parent=None):
        super().__init__(title="Camadas Ativas", icon="📐", parent=parent, radius=10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._title_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XS}px; font-weight: {Typography.WEIGHT_BOLD};
            color: {Colors.TEXT_PRIMARY}; background: transparent; border: none;
        """)
        self._rows: dict[str, _LayerRow] = {}  # label -> row
        self._hidden: set[str] = set()          # labels com olho desligado
        self._scene = None
        self.hide()

    def set_scene(self, scene):
        self._scene = scene

    def refresh(self):
        """Reconstrói as linhas com base nos item_types presentes na cena."""
        if self._scene is None:
            return

        present: set[str] = set()
        for item in self._scene.items():
            data = item.data(0)
            if not isinstance(data, dict):
                continue
            itype = data.get("item_type", "")
            if itype == "asset" and data.get("effect_key"):
                itype = "effect"
            for types, label, _icon in _LAYER_DEFS:
                if itype in types:
                    present.add(label)
                    break

        for types, label, icon in _LAYER_DEFS:
            if label in present and label not in self._rows:
                row = _LayerRow(icon, label)
                row.connect_toggle(lambda checked, lbl=label: self._on_toggle(lbl, checked))
                self.content_layout.addWidget(row)
                self._rows[label] = row
                if label in self._hidden:
                    row.set_visible_state(False)

        for label in list(self._rows):
            if label not in present:
                row = self._rows.pop(label)
                self.content_layout.removeWidget(row)
                row.deleteLater()
                self._hidden.discard(label)

        self.setVisible(bool(self._rows))

    def _on_toggle(self, label: str, checked: bool):
        if self._scene is None:
            return
        if checked:
            self._hidden.discard(label)
        else:
            self._hidden.add(label)

        types_for = {lbl: types for types, lbl, _icon in _LAYER_DEFS}
        target_types = set(types_for.get(label, []))
        is_effect = (label == "Efeitos")

        for item in self._scene.items():
            data = item.data(0)
            if not isinstance(data, dict):
                continue
            itype = data.get("item_type", "")
            if is_effect:
                if itype == "asset" and data.get("effect_key"):
                    item.setVisible(checked)
            elif itype in target_types and not data.get("effect_key"):
                item.setVisible(checked)


# ─── Element Header (internal) ─────────────────────────────────────────────

class _ElementHeader(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(90)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

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
        self._portrait = QLabel(self.image)
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._portrait.setGeometry(1, 1, 66, 66)
        self._portrait.setStyleSheet("background: transparent; border: none; border-radius: 11px;")
        self._portrait.hide()
        layout.addWidget(self.image)

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

        self.category_label = QLabel("boss")
        self.category_label.setStyleSheet(f"""
            font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
            background: {Colors.ACCENT_DIM}; border-radius: 8px;
            padding: 2px 8px; border: none;
        """)
        badges.addWidget(self.category_label)

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

    def set_element(self, name="", type_="", level="", tags="", icon="👹", pixmap: QPixmap | None = None, category=""):
        self.name_label.setText(name or "Nenhum elemento")
        self.type_label.setText(type_ or "Selecione algo no mapa")
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                66, 66, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._portrait.setPixmap(scaled)
            self._portrait.show()
            self._icon.hide()
        else:
            self._portrait.hide()
            self._icon.setText(icon)
            self._icon.show()
        if level:
            self.level_label.setText(f"⚔ Nível {level}")
            self.level_label.show()
        else:
            self.level_label.hide()
        if category:
            bg = category_badge_color(category)
            fg = category_tag_text_color(category)
            self.category_label.setText(category_label(category))
            self.category_label.setStyleSheet(f"""
                font-size: {Typography.SIZE_XXS}px; font-weight: {Typography.WEIGHT_BOLD};
                color: {fg}; background: {bg}; border-radius: 8px;
                padding: 2px 8px; border: none;
            """)
            self.category_label.show()
        else:
            self.category_label.hide()
        self.tags_label.setText(tags)
