"""DungeonsPanel — o módulo em tela cheia "Dungeons e Construções".

Duas metades lado a lado dentro de um splitter horizontal:

    ┌──── GERENCIAMENTO DA BASE ─────┬─ GERENCIAMENTO DE DUNGEONS ─┐
    │ lista │ detalhes │ árvore      │ lista │ detalhes            │
    └────────────────────────────────┴─────────────────────────────┘

Os detalhes de cada lado são pilhas de seções recolhíveis (ver
SectionEditor), não abas. As larguras são proporcionais e recalculadas a
cada resize até o usuário arrastar um divisor — mesma heurística que
MobsPanel e ItemsSkillsPanel usam.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QSplitter, QToolButton, QMenu, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors
from src.services.project_assets import import_asset, resolve_asset_path
from src.layouts.panels.dungeons.constants import DIFFICULTIES, panel_frame_style, parse_json_records
from src.layouts.panels.dungeons.record_list import RecordListColumn
from src.layouts.panels.dungeons.building_editor import BuildingEditor
from src.layouts.panels.dungeons.dungeon_editor import DungeonEditor
from src.layouts.panels.dungeons.progression_tree import ProgressionTree
from src.layouts.panels.dungeons.category_tabs import CategoryTabBar
from src.layouts.panels.dungeons.json_bulk_editor import JsonBulkEditor

logger = logging.getLogger("MAKEMAP")

# Emoji por categoria, para a lista e os nós da árvore lerem de relance sem
# cada registro precisar carregar uma imagem.
_BUILDING_ICONS = {
    "Produção": "⚒", "Defesa": "🛡", "Militar": "⚔", "Pesquisa": "🔬",
    "Armazenamento": "📦", "Social": "🏘", "Especial": "🌟",
}
_DUNGEON_ICONS = {
    "Exploração": "🗺", "Confronto": "⚔", "Enigma": "🧩",
    "Sobrevivência": "🔥", "Raide": "🐉", "Evento": "🎆",
}


class DungeonsPanel(QWidget):
    """Módulo em tela cheia de Dungeons e Construções."""

    closed = Signal()

    _HALF_RATIOS = (0.55, 0.45)
    _BASE_RATIOS = (0.24, 0.38, 0.38)
    _DUNGEON_RATIOS = (0.34, 0.66)
    _NUDGE = 6

    def __init__(self, uow, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._buildings: list[dict] = []
        self._dungeons: list[dict] = []
        self._current_building_id = ""
        self._current_dungeon_id = ""
        # Qual metade recebeu a última interação — decide sobre quem agem os
        # botões genéricos do cabeçalho (Duplicar, Exportar, Nova Entrada).
        self._focus = "building"
        self._user_dragged: set[int] = set()
        self._auto_positions: dict[int, dict[int, int]] = {}

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._building_timer = QTimer(self)
        self._building_timer.setSingleShot(True)
        self._building_timer.setInterval(400)
        self._building_timer.timeout.connect(self._save_building)
        self._dungeon_timer = QTimer(self)
        self._dungeon_timer.setSingleShot(True)
        self._dungeon_timer.setInterval(400)
        self._dungeon_timer.timeout.connect(self._save_dungeon)

        self._build_ui()
        self._refresh_building_categories()
        self._refresh_dungeon_types()
        self._reload_buildings()
        self._reload_dungeons()
        self._apply_responsive_layout()

    # ── UI ──

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 16)
        outer.setSpacing(8)
        outer.addLayout(self._build_header())

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.GLASS_BORDER}; border: none;")
        outer.addWidget(sep)

        self._halves = QSplitter(Qt.Orientation.Horizontal)
        # Collapsible=True aqui (diferente dos splitters internos de cada
        # metade) — arrastar o divisor até a esquerda ou a direita esconde
        # Gerenciamento da Base ou de Dungeons por completo, em vez de
        # parar na largura mínima de cada metade.
        self._halves.setChildrenCollapsible(True)
        self._halves.setHandleWidth(8)
        self._halves.setStyleSheet("QSplitter::handle { background: transparent; }")
        self._halves.addWidget(self._build_base_half())
        self._halves.addWidget(self._build_dungeon_half())
        self._halves.splitterMoved.connect(lambda p, i: self._on_splitter_moved(self._halves, p, i))
        outer.addWidget(self._halves, 1)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel("🏰")
        icon.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header.addWidget(icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("DUNGEONS E CONSTRUÇÕES")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14pt; font-weight: bold; background: transparent; border: none;")
        subtitle = QLabel("Projete a base do jogador e as masmorras que ele vai enfrentar.")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        for label, slot in (
            ("⬇  Importar", self._on_import),
            ("⬆  Exportar", self._on_export),
            ("⧉  Duplicar", self._on_duplicate),
        ):
            header.addWidget(self._ghost_button(label, slot))

        new_btn = QPushButton("+  Nova Entrada")
        new_btn.setFixedHeight(28)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 0 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        new_btn.clicked.connect(self._on_new_entry)
        header.addWidget(new_btn)

        gear = QToolButton()
        gear.setText("⚙")
        gear.setFixedSize(28, 28)
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.setToolTip("Opções de exibição")
        gear.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        gear.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; font-size: 12px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
            QToolButton::menu-indicator {{ image: none; }}
        """)
        menu = QMenu(gear)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("Expandir todas as seções", lambda: self._set_all_sections(True))
        menu.addAction("Recolher todas as seções", lambda: self._set_all_sections(False))
        menu.addSeparator()
        menu.addAction("Restaurar larguras das colunas", self._reset_splitters)
        gear.setMenu(menu)
        header.addWidget(gear)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none;
                font-size: 14px; border-radius: 14px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.closed.emit)
        header.addWidget(close_btn)
        return header

    def _ghost_button(self, label: str, slot) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 0 12px;
                font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; border-color: {Colors.ACCENT}; }}
        """)
        btn.clicked.connect(slot)
        return btn

    def _half_frame(self, icon: str, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 8, 10, 10)
        column.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        badge = QLabel(icon)
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {Colors.ACCENT_DIM}; border: 1px solid {Colors.BORDER_SUBTLE}; "
            f"border-radius: 8px; font-size: 14px;"
        )
        head.addWidget(badge)
        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11pt; font-weight: bold; background: transparent; border: none;")
        hint = QLabel(subtitle)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        text.addWidget(name)
        text.addWidget(hint)
        head.addLayout(text, 1)
        column.addLayout(head)
        return frame, column, head

    def _build_base_half(self) -> QFrame:
        frame, column, head = self._half_frame(
            "🏛", "GERENCIAMENTO DA BASE",
            "Crie, edite e personalize construções, defesas e a árvore de progressão.")

        self._building_json = JsonBulkEditor()
        self._building_json.apply_requested.connect(self._on_buildings_json)
        self._building_json.set_template(
            '[\n'
            '  { "name": "Ferraria", "category": "Produção", "subcategory": "Manufatura",\n'
            '    "tier": 2, "level": 1, "max_level": 5 }\n'
            ']'
        )
        head.addWidget(self._building_json.button)
        column.addWidget(self._building_json.panel)

        self._building_tabs = CategoryTabBar()
        self._building_tabs.selected.connect(lambda _k: self._refresh_building_list_view())
        self._building_tabs.create_requested.connect(self._on_building_category_create)
        self._building_tabs.rename_requested.connect(self._on_building_category_rename)
        self._building_tabs.delete_requested.connect(self._on_building_category_delete)
        column.addWidget(self._building_tabs)

        self._building_list = RecordListColumn(
            "Lista de Construções", "Buscar construção...",
            "Nova Construção", "Criar nova construção",
        )
        self._building_list.selected.connect(self._on_building_selected)
        self._building_list.new_requested.connect(self._on_new_building)
        self._building_list.image_dropped.connect(self._on_building_image_dropped)
        self._building_list.delete_requested.connect(self._on_building_delete)

        self._building_editor = BuildingEditor(buildings_provider=lambda: self._buildings)
        self._building_editor.changed.connect(self._building_timer.start)
        self._building_editor.save_requested.connect(self._save_building)
        self._building_editor.revert_requested.connect(self._revert_building)

        self._tree = ProgressionTree(
            categories_provider=lambda: self._uow.building_categories.get_all() if self._uow else [],
        )
        self._tree.selected.connect(self._on_building_selected)

        self._base_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._base_splitter.setChildrenCollapsible(False)
        self._base_splitter.setHandleWidth(8)
        self._base_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        for widget in (self._building_list, self._building_editor, self._tree):
            self._base_splitter.addWidget(widget)
        self._base_splitter.splitterMoved.connect(
            lambda p, i: self._on_splitter_moved(self._base_splitter, p, i))
        column.addWidget(self._base_splitter, 1)
        return frame

    def _build_dungeon_half(self) -> QFrame:
        frame, column, head = self._half_frame(
            "🕳", "GERENCIAMENTO DE DUNGEONS",
            "Crie, edite e personalize dungeons, encontros, recompensas e progressões.")

        self._dungeon_json = JsonBulkEditor()
        self._dungeon_json.apply_requested.connect(self._on_dungeons_json)
        self._dungeon_json.set_template(
            '[\n'
            '  { "name": "Cripta Gelada", "dungeon_type": "Exploração",\n'
            '    "level_min": 15, "level_max": 20, "difficulty": "Difícil" }\n'
            ']'
        )
        head.addWidget(self._dungeon_json.button)
        column.addWidget(self._dungeon_json.panel)

        self._dungeon_tabs = CategoryTabBar()
        self._dungeon_tabs.selected.connect(lambda _k: self._refresh_dungeon_list_view())
        self._dungeon_tabs.create_requested.connect(self._on_dungeon_type_create)
        self._dungeon_tabs.rename_requested.connect(self._on_dungeon_type_rename)
        self._dungeon_tabs.delete_requested.connect(self._on_dungeon_type_delete)
        column.addWidget(self._dungeon_tabs)

        self._dungeon_list = RecordListColumn(
            "Lista de Dungeons", "Buscar dungeons...",
            "Nova Dungeon", "Criar nova dungeon",
            filters=[("Todos os Níveis", DIFFICULTIES, "difficulty")],
        )
        self._dungeon_list.selected.connect(self._on_dungeon_selected)
        self._dungeon_list.new_requested.connect(self._on_new_dungeon)
        self._dungeon_list.image_dropped.connect(self._on_dungeon_image_dropped)
        self._dungeon_list.delete_requested.connect(self._on_dungeon_delete)

        self._dungeon_editor = DungeonEditor()
        self._dungeon_editor.changed.connect(self._dungeon_timer.start)
        self._dungeon_editor.save_requested.connect(self._save_dungeon)
        self._dungeon_editor.revert_requested.connect(self._revert_dungeon)

        self._dungeon_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._dungeon_splitter.setChildrenCollapsible(False)
        self._dungeon_splitter.setHandleWidth(8)
        self._dungeon_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        self._dungeon_splitter.addWidget(self._dungeon_list)
        self._dungeon_splitter.addWidget(self._dungeon_editor)
        self._dungeon_splitter.splitterMoved.connect(
            lambda p, i: self._on_splitter_moved(self._dungeon_splitter, p, i))
        column.addWidget(self._dungeon_splitter, 1)
        return frame

    # ── Layout responsivo ──

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _on_splitter_moved(self, splitter: QSplitter, pos: int, index: int):
        expected = self._auto_positions.get(id(splitter), {}).get(index)
        if expected is not None and abs(pos - expected) < self._NUDGE:
            return
        self._user_dragged.add(id(splitter))

    def _apply_responsive_layout(self):
        if not hasattr(self, "_halves"):
            return
        self._apply_splitter_ratio(self._halves, self._HALF_RATIOS)
        # _base_splitter/_dungeon_splitter estão ANINHADOS dentro de
        # _halves — a linha acima só agenda a nova geometria de _halves
        # (QSplitter aplica via um evento postado, não na hora), então
        # ler .width() dos splitters internos agora ainda devolveria o
        # valor de ANTES do resize. Isso é invisível num redimensionamento
        # manual gradual (cada pequeno resize já corrige o anterior antes
        # do próximo chegar), mas fica evidente num salto grande — como
        # arrastar a janela para um monitor bem menor: os dois splitters
        # internos calculam larguras a partir do tamanho antigo e ficam
        # temporariamente maiores que o espaço real, sobrepondo as três
        # colunas. Adiar para o próximo laço de eventos garante que
        # `_halves` já tenha aplicado sua própria geometria antes de os
        # splitters internos lerem a largura deles.
        QTimer.singleShot(0, self._apply_nested_splitters)

    def _apply_nested_splitters(self):
        self._apply_splitter_ratio(self._base_splitter, self._BASE_RATIOS)
        self._apply_splitter_ratio(self._dungeon_splitter, self._DUNGEON_RATIOS)

    def _apply_splitter_ratio(self, splitter: QSplitter, ratios: tuple[float, ...]):
        if id(splitter) in self._user_dragged:
            return
        width = splitter.width()
        if width <= 0:
            return
        sizes = [round(width * r) for r in ratios]
        sizes[-1] = width - sum(sizes[:-1])
        splitter.setSizes(sizes)
        self._record_auto_positions(splitter)

    def _record_auto_positions(self, splitter: QSplitter):
        actual = splitter.sizes()
        cumulative = 0
        positions: dict[int, int] = {}
        for i in range(len(actual) - 1):
            cumulative += actual[i]
            positions[i] = cumulative
        self._auto_positions[id(splitter)] = positions

    def _reset_splitters(self):
        self._user_dragged.clear()
        self._apply_responsive_layout()

    def _set_all_sections(self, expanded: bool):
        for editor in (self._building_editor, self._dungeon_editor):
            for section in editor._sections:
                section.set_expanded(expanded)

    # ── Categorias de Construção ──

    def _refresh_building_categories(self):
        """Repopula a fileira de abas + o combo "Todos os Ramos" da árvore
        — chamado no início e após criar/renomear/excluir uma aba. O
        editor de detalhes não tem mais campo de categoria (a aba já
        decide isso), então não precisa ser avisado aqui."""
        if not self._uow or not hasattr(self, "_building_tabs"):
            return
        cats = sorted(self._uow.building_categories.get_all(),
                      key=lambda c: (c.get("sort_order") or 0, c["name"]))
        self._building_tabs.set_categories(cats)
        self._tree.refresh_branch_options()

    def _on_building_category_create(self, name: str):
        if not self._uow or not name:
            return
        existing = self._uow.building_categories.get_all()
        if any(c["name"] == name for c in existing):
            return
        self._uow.building_categories.create(name=name, sort_order=len(existing))
        self._refresh_building_categories()

    def _on_building_category_rename(self, old_name: str, new_name: str):
        if not self._uow:
            return
        row = next((c for c in self._uow.building_categories.get_all() if c["name"] == old_name), None)
        if not row:
            return
        self._uow.building_categories.update(row["id"], name=new_name)
        with self._uow.db.transaction() as conn:
            conn.execute("UPDATE buildings SET category = ? WHERE category = ?", (new_name, old_name))
        self._refresh_building_categories()
        self._reload_buildings()

    def _on_building_category_delete(self, name: str):
        if not self._uow:
            return
        row = next((c for c in self._uow.building_categories.get_all() if c["name"] == name), None)
        if row:
            self._uow.building_categories.delete(row["id"])
        self._refresh_building_categories()
        self._refresh_building_list_view()

    # ── Construções ──

    def _building_row(self, b: dict) -> dict:
        return {
            "id": b["id"],
            "name": b.get("name") or "—",
            "subtitle": " • ".join(x for x in (b.get("category"), f"Nível {b.get('level') or 1}") if x),
            "icon": _BUILDING_ICONS.get(b.get("category"), "🏛"),
            "image": resolve_asset_path(self._project_dir, b.get("image") or ""),
            "status": b.get("status") or "disponivel",
            "category": b.get("category") or "",
            "code": b.get("code") or "",
        }

    def _refresh_building_list_view(self):
        """Rebuilda só a coluna da lista, filtrada pela aba ativa — sem
        reconsultar o banco (usa o cache já carregado em self._buildings).
        A árvore não é afetada: ela tem seu próprio filtro de ramo."""
        category = self._building_tabs.current() if hasattr(self, "_building_tabs") else ""
        visible = [b for b in self._buildings if not category or (b.get("category") or "") == category]
        self._building_list.set_records([self._building_row(b) for b in visible])

    def _reload_buildings(self, select_id: str | None = None):
        self._buildings = self._uow.buildings.get_all() if self._uow else []
        self._buildings.sort(key=lambda b: (int(b.get("tier") or 1),
                                            int(b.get("sort_order") or 0),
                                            b.get("name") or ""))
        self._refresh_building_list_view()
        self._tree.set_buildings([{
            "id": b["id"],
            "name": b.get("name") or "—",
            "icon": _BUILDING_ICONS.get(b.get("category"), "🏛"),
            "level": b.get("level") or 1,
            "tier": b.get("tier") or 1,
            "sort_order": b.get("sort_order") or 0,
            "status": b.get("status") or "disponivel",
            "parent_id": b.get("parent_id") or "",
            "category": b.get("category") or "",
        } for b in self._buildings])

        if select_id:
            self._on_building_selected(select_id)
        elif self._current_building_id and self._building_by_id(self._current_building_id):
            self._building_list.select(self._current_building_id)
            self._tree.select(self._current_building_id)
        else:
            self._current_building_id = ""
            self._building_editor.set_empty()

    def _building_by_id(self, building_id: str) -> dict | None:
        return next((b for b in self._buildings if b["id"] == building_id), None)

    def _load_building_into_editor(self, record: dict):
        """Passa uma cópia com a imagem resolvida para caminho absoluto —
        self._buildings continua guardando o caminho relativo (o que o
        banco tem), útil pra Exportar/Importar."""
        display = dict(record)
        display["image"] = resolve_asset_path(self._project_dir, record.get("image") or "")
        self._building_editor.load(display)

    def _on_building_selected(self, building_id: str):
        record = self._building_by_id(building_id)
        if not record:
            return
        self._focus = "building"
        self._current_building_id = building_id
        self._building_list.select(building_id)
        self._tree.select(building_id)
        self._load_building_into_editor(record)

    def _on_new_building(self):
        if not self._uow:
            return
        building_id = str(uuid.uuid4())
        # "Solta na aba que você está navegando" — mesmo espírito do "+ Novo
        # Mob" dentro de uma pasta (CategoryExplorerMixin). Com "Todas"
        # ativa, cai na primeira categoria cadastrada.
        category = self._building_tabs.current() or next(
            iter(self._uow.building_categories.get_all()), {}).get("name", "")
        self._uow.buildings.create(
            id=building_id,
            code=self._next_code("BLD_", [b.get("code", "") for b in self._buildings]),
            name="Nova Construção", category=category, subcategory="",
            level=1, max_level=5, tier=1, status="disponivel",
        )
        self._reload_buildings(select_id=building_id)
        logger.info("Nova construção criada: id=%s", building_id)

    def _save_building(self):
        if not self._uow or not self._current_building_id:
            return
        values = self._building_editor.collect()
        if values.get("image"):
            values["image"] = import_asset(
                self._project_dir, values["image"], "assets/buildings", self._current_building_id)
        self._uow.buildings.update(self._current_building_id, **values)
        record = self._building_by_id(self._current_building_id)
        if record:
            record.update(values)
        self._reload_buildings()

    def _revert_building(self):
        if not self._uow or not self._current_building_id:
            return
        self._building_timer.stop()
        record = self._uow.buildings.get(self._current_building_id)
        if record:
            self._load_building_into_editor(record)

    def _on_building_image_dropped(self, record_id: str, path: str):
        if not self._uow:
            return
        relative = import_asset(self._project_dir, path, "assets/buildings", record_id)
        self._uow.buildings.update(record_id, image=relative)
        self._reload_buildings()

    def _on_building_delete(self, building_id: str):
        if not self._uow:
            return
        record = self._building_by_id(building_id)
        name = record.get("name") if record else building_id
        reply = QMessageBox.question(
            self, "Excluir construção",
            f'Excluir "{name}"? Construções que dependem dela na árvore de '
            "progressão ficam sem construção-mãe, sem serem apagadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._uow.buildings.delete(building_id)
        if self._current_building_id == building_id:
            self._current_building_id = ""
        self._reload_buildings()
        logger.info("Construção excluída: id=%s", building_id)

    def _on_buildings_json(self, text: str):
        if not self._uow:
            return
        try:
            records = parse_json_records(text)
        except ValueError as exc:
            self._building_json.show_error(str(exc))
            return
        fallback_category = self._building_tabs.current() or next(
            iter(self._uow.building_categories.get_all()), {}).get("name", "")
        existing_categories = {c["name"] for c in self._uow.building_categories.get_all()}
        codes = [b.get("code", "") for b in self._buildings]
        last_id = None
        for rec in records:
            category = str(rec.get("category") or fallback_category)
            # A categoria citada no JSON pode não existir ainda como aba —
            # cria na hora, em vez de descartar ou cair num valor genérico.
            if category and category not in existing_categories:
                self._uow.building_categories.create(name=category, sort_order=len(existing_categories))
                existing_categories.add(category)
            building_id = str(uuid.uuid4())
            code = self._next_code("BLD_", codes)
            codes.append(code)
            self._uow.buildings.create(
                id=building_id, code=code,
                name=str(rec.get("name") or "Nova Construção"),
                category=category,
                subcategory=str(rec.get("subcategory") or ""),
                level=int(rec.get("level") or 1),
                max_level=int(rec.get("max_level") or 5),
                tier=int(rec.get("tier") or 1),
                status=str(rec.get("status") or "disponivel"),
            )
            last_id = building_id
        self._building_json.close()
        self._refresh_building_categories()
        self._reload_buildings(select_id=last_id)
        logger.info("Construções criadas via JSON: %d", len(records))

    # ── Tipos de Dungeon ──

    def _refresh_dungeon_types(self):
        """O editor de detalhes não tem mais campo de tipo (a aba já decide
        isso), então só a fileira de abas precisa ser repopulada aqui."""
        if not self._uow or not hasattr(self, "_dungeon_tabs"):
            return
        types = sorted(self._uow.dungeon_types.get_all(),
                       key=lambda t: (t.get("sort_order") or 0, t["name"]))
        self._dungeon_tabs.set_categories(types)

    def _on_dungeon_type_create(self, name: str):
        if not self._uow or not name:
            return
        existing = self._uow.dungeon_types.get_all()
        if any(t["name"] == name for t in existing):
            return
        self._uow.dungeon_types.create(name=name, sort_order=len(existing))
        self._refresh_dungeon_types()

    def _on_dungeon_type_rename(self, old_name: str, new_name: str):
        if not self._uow:
            return
        row = next((t for t in self._uow.dungeon_types.get_all() if t["name"] == old_name), None)
        if not row:
            return
        self._uow.dungeon_types.update(row["id"], name=new_name)
        with self._uow.db.transaction() as conn:
            conn.execute("UPDATE dungeons SET dungeon_type = ? WHERE dungeon_type = ?", (new_name, old_name))
        self._refresh_dungeon_types()
        self._reload_dungeons()

    def _on_dungeon_type_delete(self, name: str):
        if not self._uow:
            return
        row = next((t for t in self._uow.dungeon_types.get_all() if t["name"] == name), None)
        if row:
            self._uow.dungeon_types.delete(row["id"])
        self._refresh_dungeon_types()
        self._refresh_dungeon_list_view()

    # ── Dungeons ──

    def _dungeon_row(self, d: dict) -> dict:
        return {
            "id": d["id"],
            "name": d.get("name") or "—",
            "subtitle": f"{d.get('dungeon_type') or '—'} • Nível "
                        f"{d.get('level_min') or 1}-{d.get('level_max') or 1}",
            "icon": _DUNGEON_ICONS.get(d.get("dungeon_type"), "🕳"),
            "image": resolve_asset_path(self._project_dir, d.get("image") or ""),
            "status": "concluida" if d.get("active", 1) else "bloqueada",
            "dungeon_type": d.get("dungeon_type") or "",
            "difficulty": d.get("difficulty") or "",
            "code": d.get("code") or "",
        }

    def _refresh_dungeon_list_view(self):
        dungeon_type = self._dungeon_tabs.current() if hasattr(self, "_dungeon_tabs") else ""
        visible = [d for d in self._dungeons if not dungeon_type or (d.get("dungeon_type") or "") == dungeon_type]
        self._dungeon_list.set_records([self._dungeon_row(d) for d in visible])

    def _reload_dungeons(self, select_id: str | None = None):
        self._dungeons = self._uow.dungeons.get_all() if self._uow else []
        self._dungeons.sort(key=lambda d: (int(d.get("level_min") or 0), d.get("name") or ""))
        self._refresh_dungeon_list_view()

        if select_id:
            self._on_dungeon_selected(select_id)
        elif self._current_dungeon_id and self._dungeon_by_id(self._current_dungeon_id):
            self._dungeon_list.select(self._current_dungeon_id)
        else:
            self._current_dungeon_id = ""
            self._dungeon_editor.set_empty()

    def _dungeon_by_id(self, dungeon_id: str) -> dict | None:
        return next((d for d in self._dungeons if d["id"] == dungeon_id), None)

    def _load_dungeon_into_editor(self, record: dict):
        display = dict(record)
        display["image"] = resolve_asset_path(self._project_dir, record.get("image") or "")
        self._dungeon_editor.load(display)

    def _on_dungeon_selected(self, dungeon_id: str):
        record = self._dungeon_by_id(dungeon_id)
        if not record:
            return
        self._focus = "dungeon"
        self._current_dungeon_id = dungeon_id
        self._dungeon_list.select(dungeon_id)
        self._load_dungeon_into_editor(record)

    def _on_new_dungeon(self):
        if not self._uow:
            return
        dungeon_id = str(uuid.uuid4())
        default_type = self._dungeon_tabs.current() or next(
            iter(self._uow.dungeon_types.get_all()), {}).get("name", "")
        self._uow.dungeons.create(
            id=dungeon_id,
            code=self._next_code("DGN_", [d.get("code", "") for d in self._dungeons]),
            name="Nova Dungeon", dungeon_type=default_type, difficulty="Normal",
            level_min=1, level_max=10, rooms=1, active=1, visible_on_map=1,
        )
        self._reload_dungeons(select_id=dungeon_id)
        logger.info("Nova dungeon criada: id=%s", dungeon_id)

    def _save_dungeon(self):
        if not self._uow or not self._current_dungeon_id:
            return
        values = self._dungeon_editor.collect()
        if values.get("image"):
            values["image"] = import_asset(
                self._project_dir, values["image"], "assets/dungeons", self._current_dungeon_id)
        self._uow.dungeons.update(self._current_dungeon_id, **values)
        record = self._dungeon_by_id(self._current_dungeon_id)
        if record:
            record.update(values)
        self._reload_dungeons()

    def _revert_dungeon(self):
        if not self._uow or not self._current_dungeon_id:
            return
        self._dungeon_timer.stop()
        record = self._uow.dungeons.get(self._current_dungeon_id)
        if record:
            self._load_dungeon_into_editor(record)

    def _on_dungeon_image_dropped(self, record_id: str, path: str):
        if not self._uow:
            return
        relative = import_asset(self._project_dir, path, "assets/dungeons", record_id)
        self._uow.dungeons.update(record_id, image=relative)
        self._reload_dungeons()

    def _on_dungeon_delete(self, dungeon_id: str):
        if not self._uow:
            return
        record = self._dungeon_by_id(dungeon_id)
        name = record.get("name") if record else dungeon_id
        reply = QMessageBox.question(
            self, "Excluir dungeon", f'Excluir "{name}"? Essa ação não pode ser desfeita.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._uow.dungeons.delete(dungeon_id)
        if self._current_dungeon_id == dungeon_id:
            self._current_dungeon_id = ""
        self._reload_dungeons()
        logger.info("Dungeon excluída: id=%s", dungeon_id)

    def _on_dungeons_json(self, text: str):
        if not self._uow:
            return
        try:
            records = parse_json_records(text)
        except ValueError as exc:
            self._dungeon_json.show_error(str(exc))
            return
        fallback_type = self._dungeon_tabs.current() or next(
            iter(self._uow.dungeon_types.get_all()), {}).get("name", "")
        existing_types = {t["name"] for t in self._uow.dungeon_types.get_all()}
        codes = [d.get("code", "") for d in self._dungeons]
        last_id = None
        for rec in records:
            dungeon_type = str(rec.get("dungeon_type") or fallback_type)
            # O tipo citado no JSON pode não existir ainda como aba — cria
            # na hora, em vez de descartar ou cair num valor genérico.
            if dungeon_type and dungeon_type not in existing_types:
                self._uow.dungeon_types.create(name=dungeon_type, sort_order=len(existing_types))
                existing_types.add(dungeon_type)
            dungeon_id = str(uuid.uuid4())
            code = self._next_code("DGN_", codes)
            codes.append(code)
            self._uow.dungeons.create(
                id=dungeon_id, code=code,
                name=str(rec.get("name") or "Nova Dungeon"),
                dungeon_type=dungeon_type,
                difficulty=str(rec.get("difficulty") or "Normal"),
                level_min=int(rec.get("level_min") or 1),
                level_max=int(rec.get("level_max") or 10),
                biome=str(rec.get("biome") or ""),
                rooms=int(rec.get("rooms") or 1),
                active=1, visible_on_map=1,
            )
            last_id = dungeon_id
        self._dungeon_json.close()
        self._refresh_dungeon_types()
        self._reload_dungeons(select_id=last_id)
        logger.info("Dungeons criadas via JSON: %d", len(records))

    # ── Ações do cabeçalho ──

    def _on_new_entry(self):
        """Cria na metade que recebeu a última interação."""
        if self._focus == "dungeon":
            self._on_new_dungeon()
        else:
            self._on_new_building()

    def _on_duplicate(self):
        if not self._uow:
            return
        if self._focus == "dungeon":
            source = self._dungeon_by_id(self._current_dungeon_id)
            if not source:
                return
            clone = {k: v for k, v in source.items()
                     if k not in ("id", "created_at", "updated_at")}
            clone["id"] = str(uuid.uuid4())
            clone["name"] = f"{source.get('name', 'Dungeon')} (cópia)"
            clone["code"] = self._next_code("DGN_", [d.get("code", "") for d in self._dungeons])
            self._uow.dungeons.create(**clone)
            self._reload_dungeons(select_id=clone["id"])
        else:
            source = self._building_by_id(self._current_building_id)
            if not source:
                return
            clone = {k: v for k, v in source.items()
                     if k not in ("id", "created_at", "updated_at")}
            clone["id"] = str(uuid.uuid4())
            clone["name"] = f"{source.get('name', 'Construção')} (cópia)"
            clone["code"] = self._next_code("BLD_", [b.get("code", "") for b in self._buildings])
            self._uow.buildings.create(**clone)
            self._reload_buildings(select_id=clone["id"])

    def _on_export(self):
        """Grava a metade em foco como JSON — as duas listas inteiras, não
        só o registro selecionado."""
        which = "dungeons" if self._focus == "dungeon" else "construcoes"
        path, _ = QFileDialog.getSaveFileName(self, f"Exportar {which}", f"{which}.json", "JSON (*.json)")
        if not path:
            return
        records = self._dungeons if self._focus == "dungeon" else self._buildings
        payload = [{k: v for k, v in r.items() if k not in ("created_at", "updated_at")}
                   for r in records]
        try:
            Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Exportado %s: %d registros → %s", which, len(payload), path)
        except OSError as exc:
            logger.warning("Falha ao exportar %s: %s", which, exc)

    def _on_import(self):
        """Lê um JSON no mesmo formato do Exportar e cria os registros. Ids
        são regerados, então importar duas vezes duplica em vez de
        sobrescrever o que já existe."""
        if not self._uow:
            return
        which = "dungeons" if self._focus == "dungeon" else "construções"
        path, _ = QFileDialog.getOpenFileName(self, f"Importar {which}", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Falha ao importar %s: %s", which, exc)
            return
        if not isinstance(data, list):
            logger.warning("Importação ignorada: esperava uma lista de registros")
            return

        repo = self._uow.dungeons if self._focus == "dungeon" else self._uow.buildings
        columns = self._table_columns(repo.TABLE)
        last_id = None
        for record in data:
            if not isinstance(record, dict) or not record.get("name"):
                continue
            fields = {k: v for k, v in record.items() if k in columns and k != "id"}
            # parent_id aponta para um id do arquivo de origem, que não
            # existe aqui — a hierarquia é refeita à mão depois.
            fields.pop("parent_id", None)
            fields["id"] = str(uuid.uuid4())
            repo.create(**fields)
            last_id = fields["id"]
        if self._focus == "dungeon":
            self._reload_dungeons(select_id=last_id)
        else:
            self._reload_buildings(select_id=last_id)
        logger.info("Importados %d registros de %s", len(data), which)

    def _table_columns(self, table: str) -> set[str]:
        rows = self._uow.db.fetchall(f"PRAGMA table_info({table})")
        return {row["name"] for row in rows}

    @staticmethod
    def _next_code(prefix: str, existing: list[str], start: int = 1) -> str:
        max_n = start - 1
        for code in existing:
            if code and code.startswith(prefix):
                tail = code[len(prefix):]
                if tail.isdigit():
                    max_n = max(max_n, int(tail))
        return f"{prefix}{max_n + 1:04d}"

    # ── paint (mesmo cartão de vidro dos outros módulos) ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        p.fillPath(path, QColor(14, 22, 42, 230))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
        p.drawPath(path)
        p.end()
