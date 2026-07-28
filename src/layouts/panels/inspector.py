"""4. Inspector + 4.1 Quest + 4.2 Layers — 3 painéis independentes colapsáveis."""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QToolButton,
    QTabWidget, QWidget, QSizePolicy, QSlider, QScrollArea,
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


# ─── Read-only info rows (mob data — Inspector is a quick-view, the actual
# editing surface is the Mobs module's own edit panel) ──────────────────────

# 2 fields per row (label stacked above value, not side-by-side) instead of
# one full-width row per field — same info in roughly half the height.
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
    """A tab of read-only fields built from a (label, mob_dict_key,
    formatter) spec, laid out _INFO_GRID_COLS-per-row — every key here must
    be a real column the Mobs module's edit panel actually reads/writes
    (see edit_overview_mixin/edit_atributos_mixin/edit_extras_mixin), so
    nothing shown is a field that doesn't exist."""

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
    """A QScrollArea wrapping a QVBoxLayout of rows (see _fill_grid) — every
    row is its own QHBoxLayout holding up to 5 tiles plus a trailing
    addStretch(), so leftover width always lands after the last tile in
    that row, never between tiles. Two earlier attempts at this (plain
    QGridLayout, then QGridLayout + setColumnStretch, then QGridLayout + a
    fixed-width container) all still left Qt free to space the tiles out
    somewhere in the layout — a manual row of fixed-size widgets with one
    trailing stretch has no such ambiguity: everything before the stretch
    keeps its own sizeHint width, period. The QScrollArea still guarantees
    rows beyond the first stay reachable, same as before."""
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
    """How wide a tile can be and still fit _GRID_COLS per row inside
    `scroll`'s current viewport — computed from the real rendered width
    instead of a guessed constant, so tiles actually fill the row (a fixed
    small size like 28px left a lot of unused width on the right once the
    "gap between tiles" bug itself was fixed) rather than leaving empty
    space to be conservative about widths this module can't know ahead of
    time (splitter drags, different screens, etc.)."""
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
    """GERAL tab body — the flat key/value rows (_InfoTab/_GERAL_SPEC) plus
    Drops/Habilidades as small square tiles (_DropTile/_CatalogTile — same
    shape as the Mobs edit panel's own search-grid picker, see
    edit_widgets.py, just smaller), wrapped/scrolled the same way the
    Brush panel's asset grid is (see _tile_scroll_grid). Read-only:
    Inspector only displays — removing a drop/habilidade is done from the
    Mobs edit panel itself, so _DropTile is built with removable=False
    (no "✕") and _CatalogTile's `clicked` signal is never connected here."""

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
        # Grown from a tight 2-row cap to a real share of the tab's height
        # (stretch factor below) now that the GERAL fields above take half
        # the vertical space they used to (see _InfoTab's grid layout).
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
        # Measuring viewport widths synchronously here — even after forcing
        # this widget's own layout().activate() — still read stale/too-wide
        # numbers for Habilidades specifically, because the width that
        # actually needs to settle first lives further up the ancestor
        # chain (CollapsiblePanel / the floating Inspector panel itself),
        # not just in _GeralTab's own layout. QTimer.singleShot(0, …) defers
        # the actual measuring + tile-building to the next iteration of
        # Qt's event loop, by which point every pending resize/layout event
        # anywhere in that chain has genuinely been processed.
        QTimer.singleShot(0, lambda: self._fill_tiles(drops, abilities))

    def _fill_tiles(self, drops: list[tuple[dict, float, int]], abilities: list[tuple[dict, bool]]):
        drop_size = _row_tile_width(self._drops_scroll)  # _DropTile's own width == size
        _fill_grid(self._drops_grid, [
            _DropTile(item_dict, rate, qty, size=drop_size, removable=False)
            for item_dict, rate, qty in drops
        ])

        # _CatalogTile's own width is size+16 (edit_widgets.py), so back out
        # the +16 to land on the same per-row tile width as Drops above.
        ability_size = max(_MIN_TILE_SIZE, _row_tile_width(self._abilities_scroll) - 16)
        _fill_grid(self._abilities_grid, [
            _CatalogTile(skill, size=ability_size) for skill, _unlinked in abilities
        ])


# Every key below is a real column the Mobs module's edit panel reads/writes
# (see edit_overview_mixin.py, edit_atributos_mixin.py) — nothing here is a
# placeholder field with no backing data. Drops/Habilidades aren't flat
# key -> string values (they're catalog-linked cards, see _GeralTab below),
# so they're handled outside this spec instead of through _InfoTab.
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
    ("Status", "status", None),
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
    """4. Inspector — header + abas com dados reais do elemento selecionado
    no mapa (colapsável). Read-only: a edição de verdade acontece no painel
    de edição do próprio módulo (ex.: Mobs)."""

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
        """Populates the header + every tab from a real mob dict (same
        shape the Mobs module's edit panel reads/writes) — `region_name`,
        `drops` and `abilities` are passed in already-resolved against the
        Item/Skill catalogs since Inspector has no DB access of its own
        (see SpawnMediator._on_selection_changed)."""
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

    def clear(self):
        self.header.set_element()
        self._clear_tabs()

    def _clear_tabs(self):
        for tab in (self._geral_tab, self._atributos_tab, self._ia_tab, self._outros_tab):
            tab.set_data(None)


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
        self._portrait = QLabel(self.image)
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._portrait.setGeometry(1, 1, 66, 66)
        self._portrait.setStyleSheet("background: transparent; border: none; border-radius: 11px;")
        self._portrait.hide()
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

        # Same category chip the Mobs grid card/Visão Geral use (see
        # categories.category_badge_color) — colored per-category from the
        # live mob_categories lookup, not a hardcoded palette.
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


