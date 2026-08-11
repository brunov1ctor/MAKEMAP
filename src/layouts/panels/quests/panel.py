"""QuestsPanel — o módulo em tela cheia "Quests".

Três colunas lado a lado dentro de um splitter horizontal, igual ao layout
de referência:

    ┌─ lista ─┬──────── conteúdo (abas) ────────┬─ propriedades ─┐
    │ quests  │ Fluxo/Geral/Objetivos/.../Notas  │ da quest       │
    └─────────┴──────────────────────────────────┴────────────────┘

8 das 9 abas têm edição de verdade: Fluxo (grafo de nós — ver flow_tab.py/
flow_canvas.py/flow_node.py), Geral (cadeia de missão), Objetivos e
Condições/Eventos (EditableRowList sobre suas colunas JSON), NPCs e
Diálogos (quest_npcs + texto livre), Scripts e Notas (texto livre).
"Recompensas" continua placeholder como aba de conteúdo — a edição de
recompensas de verdade mora no painel de propriedades à direita (ver
properties_panel.py), que é 3 cartões separados (Propriedades da Quest /
Configurações / Recompensas), sempre visíveis independente da aba ativa.
"""

from __future__ import annotations

import logging
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QStackedWidget, QComboBox, QToolButton, QMenu,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors, combo_qss
from src.components.live_splitter import LiveSplitter
from src.services.project_assets import import_asset, resolve_asset_path
from src.layouts.panels.quests.record_list import RecordListColumn
from src.layouts.panels.quests.constants import (
    panel_frame_style, sub_header, _no_wheel, STATUS_LABELS, QUEST_TYPES, CONTENT_TABS,
    hrule, json_obj,
)
from src.layouts.panels.quests.tab_bar import ContentTabBar
from src.layouts.panels.quests.flow_tab import FlowTab
from src.layouts.panels.quests.general_tab import GeneralTab
from src.layouts.panels.quests.objectives_tab import ObjectivesTab
from src.layouts.panels.quests.npcs_dialogs_tab import NpcsDialogsTab
from src.layouts.panels.quests.conditions_tab import ConditionsTab
from src.layouts.panels.quests.events_tab import EventsTab
from src.layouts.panels.quests.text_field_tab import TextFieldTab
from src.layouts.panels.quests.properties_panel import QuestPropertiesPanel
from src.layouts.panels.quests.panel_import_export_mixin import QuestsImportExportMixin

logger = logging.getLogger("MAKEMAP")

_TYPE_ICONS = {
    "Principal": "★", "Secundária": "◆", "Diária": "☀", "Semanal": "🗓",
    "Evento": "🎆", "Cadeia": "🔗",
}


class QuestsPanel(QuestsImportExportMixin, QWidget):
    """Módulo em tela cheia de Quests."""

    closed = Signal()

    _COL_RATIOS = (0.22, 0.53, 0.25)
    _NUDGE = 6

    def __init__(self, uow, project_dir=None, scene_provider=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        # Callback (not the engine itself) so this fullscreen panel can feed
        # a live mini-map preview (Fluxo tab) the SAME QGraphicsScene the
        # main map uses, without holding a direct reference to the canvas
        # engine — same "inject a bound method, not the object" idiom
        # MenuViewMediator already uses for zones_provider/zone_thumbnail_
        # provider on MobsPanel/NPCsPanel.
        self._scene_provider = scene_provider or (lambda: None)
        self._quests: list[dict] = []
        self._chains: list[dict] = []
        self._regions: list[dict] = []
        self._current_quest_id = ""
        self._user_dragged: set[int] = set()
        self._auto_positions: dict[int, dict[int, int]] = {}

        # QuestsImportExportMixin state
        self._tools_mode: str | None = None
        self._template_fmt: str = "json"

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_quest)

        self._build_ui()
        self._reload_regions()
        self._reload_items_menu()
        self._reload_npcs_menu()
        self._reload_mobs_menu()
        self._reload_chains()
        self._reload_quests()
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

        self._splitter = LiveSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(8)
        self._splitter.addWidget(self._build_list_column())
        self._splitter.addWidget(self._build_content_column())
        self._splitter.addWidget(self._build_properties_column())
        self._splitter.splitterMoved.connect(lambda p, i: self._on_splitter_moved(p, i))

        # ── Body stack: normal 3-column view vs. the Importar/Exportar
        # tools panel (QuestsImportExportMixin) — same pattern
        # DungeonsPanel/ItemsSkillsPanel use, since neither has a spare
        # column to take over. ──
        self._body_stack = QStackedWidget()
        self._body_stack.addWidget(self._splitter)
        self._body_stack.addWidget(self._build_tools_panel())
        outer.addWidget(self._body_stack, 1)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel("📜")
        icon.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header.addWidget(icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("QUESTS")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14pt; font-weight: bold; background: transparent; border: none;")
        subtitle = QLabel("Crie missões, objetivos e recompensas para seus jogadores.")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        import_btn = QPushButton("📥 Importar")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 5px 12px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); border-color: {Colors.ACCENT}; }}
        """)
        import_btn.clicked.connect(self._toggle_import_mode)
        header.addWidget(import_btn)

        export_btn = QToolButton()
        export_btn.setText("📤 Exportar")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 5px 12px; font-size: 10px; }}
            QToolButton::menu-indicator {{ image: none; }}
            QToolButton:hover {{ background: rgba(255,255,255,0.12); border-color: {Colors.ACCENT}; }}
        """)
        export_menu = QMenu(export_btn)
        export_menu.addAction("Exportar como JSON", lambda: self._on_export_choice("json"))
        export_menu.addAction("Exportar como CSV", lambda: self._on_export_choice("csv"))
        export_menu.addAction("Exportar como Excel", lambda: self._on_export_choice("xlsx"))
        export_btn.setMenu(export_menu)
        header.addWidget(export_btn)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none;
                font-size: 14px; border-radius: 14px; padding: 0; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self._on_close_clicked)
        header.addWidget(close_btn)
        return header

    def _build_list_column(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setMinimumWidth(220)
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(8)

        new_btn = QPushButton("+  Nova Quest")
        new_btn.setFixedHeight(28)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 0 10px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        new_btn.clicked.connect(self._on_new_quest)
        column.addWidget(new_btn)

        region_names = [r.get("name", "") for r in (self._uow.regions.get_all() if self._uow else [])]
        self._quest_list = RecordListColumn(
            "Quests", "Buscar quests...",
            filters=[("Todas as regiões", sorted(region_names), "region"),
                     ("Todos os status", STATUS_LABELS, "status")],
        )
        self._quest_list.selected.connect(self._on_quest_selected)
        self._quest_list.image_dropped.connect(self._on_quest_image_dropped)
        self._quest_list.delete_requested.connect(self._on_quest_delete)
        column.addWidget(self._quest_list, 1)
        column.addWidget(self._build_summary_card())
        return frame

    def _build_summary_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        lay.addWidget(sub_header("Resumo do Projeto"))

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self._summary_total = self._summary_stat(top_row, "📖", "Total de Quests")
        self._summary_active = self._summary_stat(top_row, "🌿", "Ativas")
        self._summary_progress = self._summary_stat(top_row, "⏳", "Em progresso")
        lay.addLayout(top_row)
        lay.addWidget(hrule())

        self._summary_level = self._summary_line(lay, "Nível médio")
        self._summary_exp = self._summary_line(lay, "EXP total")
        self._summary_items = self._summary_line(lay, "Itens como recompensa")
        self._summary_npcs = self._summary_line(lay, "NPCs envolvidos")
        return frame

    @staticmethod
    def _summary_stat(row: QHBoxLayout, icon: str, label_text: str) -> QLabel:
        col = QVBoxLayout()
        col.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(3)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        value_lbl = QLabel("0")
        value_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        top.addWidget(icon_lbl)
        top.addWidget(value_lbl)
        top.addStretch()
        col.addLayout(top)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        col.addWidget(label)
        row.addLayout(col, 1)
        return value_lbl

    @staticmethod
    def _summary_line(lay: QVBoxLayout, label_text: str) -> QLabel:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
        value = QLabel("0")
        value.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        row.addWidget(label, 1)
        row.addWidget(value)
        lay.addLayout(row)
        return value

    def _refresh_summary(self):
        if not hasattr(self, "_summary_total"):
            return
        total = len(self._quests)
        active = sum(1 for q in self._quests if q.get("status") == "Ativa")
        progress = sum(1 for q in self._quests if q.get("status") == "Em progresso")
        levels = [int(q.get("level_req") or 1) for q in self._quests]
        avg_level = round(sum(levels) / len(levels)) if levels else 0

        total_exp = 0
        total_reward_items = 0
        for q in self._quests:
            rewards = json_obj(q.get("rewards"))
            total_exp += int(rewards.get("exp") or 0)
            total_reward_items += len(rewards.get("items") or [])

        npcs_involved = len(self._uow.quest_npcs.distinct_npc_ids()) if self._uow else 0

        self._summary_total.setText(str(total))
        self._summary_active.setText(str(active))
        self._summary_progress.setText(str(progress))
        self._summary_level.setText(str(avg_level))
        self._summary_exp.setText(f"{total_exp:,}".replace(",", "."))
        self._summary_items.setText(str(total_reward_items))
        self._summary_npcs.setText(str(npcs_involved))

    def _build_content_column(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setMinimumWidth(360)
        column = QVBoxLayout(frame)
        column.setContentsMargins(12, 10, 12, 10)
        column.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._content_icon = QLabel("★")
        self._content_icon.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14px; background: transparent; border: none;")
        title_row.addWidget(self._content_icon)
        self._content_title = QLabel("Nenhuma quest selecionada")
        self._content_title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13pt; font-weight: bold; background: transparent; border: none;")
        title_row.addWidget(self._content_title, 1)

        self._status_combo = QComboBox()
        self._status_combo.addItems(STATUS_LABELS)
        _no_wheel(self._status_combo)
        self._status_combo.setStyleSheet(combo_qss(padding="3px 8px"))
        self._status_combo.currentTextChanged.connect(self._on_status_changed)
        title_row.addWidget(self._status_combo)

        self._code_lbl = QLabel("")
        self._code_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        title_row.addWidget(self._code_lbl)
        column.addLayout(title_row)

        self._tabs = ContentTabBar(CONTENT_TABS)
        self._tabs.selected.connect(self._on_tab_selected)
        column.addWidget(self._tabs)

        self._stack = QStackedWidget()
        self._tab_index: dict[str, int] = {}
        for key, icon, label in CONTENT_TABS:
            if key == "fluxo":
                self._flow_tab = FlowTab(scene_provider=self._scene_provider)
                self._flow_tab.changed.connect(self._save_timer.start)
                page = self._flow_tab
            elif key == "geral":
                self._general_tab = GeneralTab()
                self._general_tab.changed.connect(self._save_timer.start)
                self._general_tab.chain_create_requested.connect(self._on_chain_create)
                page = self._general_tab
            elif key == "objetivos":
                self._objectives_tab = ObjectivesTab()
                self._objectives_tab.changed.connect(self._save_timer.start)
                page = self._objectives_tab
            elif key == "npcs_dialogos":
                self._npcs_tab = NpcsDialogsTab()
                self._npcs_tab.changed.connect(self._save_timer.start)
                page = self._npcs_tab
            elif key == "condicoes":
                self._conditions_tab = ConditionsTab()
                self._conditions_tab.changed.connect(self._save_timer.start)
                page = self._conditions_tab
            elif key == "eventos":
                self._events_tab = EventsTab()
                self._events_tab.changed.connect(self._save_timer.start)
                page = self._events_tab
            elif key == "scripts":
                self._scripts_tab = TextFieldTab(
                    "Scripts", "Hooks de script (ex.: Lua) que rodam nos eventos desta quest.",
                    "scripts", placeholder="-- cole aqui o script...", monospace=True,
                )
                self._scripts_tab.changed.connect(self._save_timer.start)
                page = self._scripts_tab
            elif key == "notas":
                self._notes_tab = TextFieldTab(
                    "Notas", "Anotações livres do designer — não aparece pro jogador.",
                    "notes", placeholder="Anotações...",
                )
                self._notes_tab.changed.connect(self._save_timer.start)
                page = self._notes_tab
            else:
                page = self._build_placeholder_tab(icon, label)
            self._tab_index[key] = self._stack.addWidget(page)
        column.addWidget(self._stack, 1)
        return frame

    def _build_placeholder_tab(self, icon: str, label: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        lay = QVBoxLayout(frame)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 34px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)
        msg = QLabel(f"{label}")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11pt; background: transparent; border: none;")
        lay.addWidget(msg)
        hint = QLabel("Em breve...")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; font-style: italic; background: transparent; border: none;")
        lay.addWidget(hint)
        return frame

    def _build_properties_column(self) -> QuestPropertiesPanel:
        self._properties = QuestPropertiesPanel()
        self._properties.changed.connect(self._save_timer.start)
        return self._properties

    # ── Layout responsivo ──

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _on_splitter_moved(self, pos: int, index: int):
        expected = self._auto_positions.get(index)
        if expected is not None and abs(pos - expected) < self._NUDGE:
            return
        self._user_dragged.add(id(self._splitter))

    def _apply_responsive_layout(self):
        if not hasattr(self, "_splitter") or id(self._splitter) in self._user_dragged:
            return
        width = self._splitter.width()
        if width <= 0:
            return
        sizes = [round(width * r) for r in self._COL_RATIOS]
        sizes[-1] = width - sum(sizes[:-1])
        self._splitter.setSizes(sizes)
        actual = self._splitter.sizes()
        cumulative = 0
        positions: dict[int, int] = {}
        for i in range(len(actual) - 1):
            cumulative += actual[i]
            positions[i] = cumulative
        self._auto_positions = positions

    # ── Abas de conteúdo ──

    def _on_tab_selected(self, key: str):
        self._stack.setCurrentIndex(self._tab_index.get(key, 0))

    # ── Regiões / catálogo de itens (para o painel de propriedades) ──

    def _reload_regions(self):
        self._regions = sorted(
            self._uow.regions.get_all() if self._uow else [],
            key=lambda r: r.get("name", ""),
        )
        self._properties.set_regions(self._regions)

    def _reload_items_menu(self):
        items = self._uow.items.get_all() if self._uow else []
        self._properties.set_items_catalog(sorted(items, key=lambda i: i.get("name", "")))

    def _reload_npcs_menu(self):
        self._npcs_catalog = sorted(
            self._uow.npcs.get_all() if self._uow else [], key=lambda n: n.get("name", ""))
        self._npcs_tab.set_npcs(self._npcs_catalog)
        self._refresh_flow_catalog()

    def _reload_mobs_menu(self):
        self._mobs_catalog = sorted(
            self._uow.mobs.get_all() if self._uow else [], key=lambda m: m.get("name", ""))
        self._refresh_flow_catalog()

    def _refresh_flow_catalog(self):
        """O picker "Vincular a" do editor de nós do Fluxo lista os mesmos
        NPCs/Mobs cadastrados no projeto — atualizado depois de qualquer
        reload de qualquer um dos dois catálogos, já que os dois chegam em
        momentos diferentes do __init__."""
        self._flow_tab.set_catalog(
            getattr(self, "_npcs_catalog", []), getattr(self, "_mobs_catalog", []))

    # ── Cadeias de Quest ──

    def _reload_chains(self):
        self._chains = self._uow.quest_chains.get_all() if self._uow else []
        self._chains.sort(key=lambda c: c.get("name", ""))
        self._general_tab.set_chains(self._chains)

    def _chain_by_name(self, name: str) -> dict | None:
        return next((c for c in self._chains if c.get("name") == name), None)

    def _on_chain_create(self, name: str):
        if not self._uow or not name:
            return
        self._uow.quest_chains.create(name=name)
        self._reload_chains()

    def _refresh_chain_quests_preview(self):
        record = self._quest_by_id(self._current_quest_id)
        chain_id = record.get("chain_id") if record else ""
        if not chain_id:
            self._general_tab.set_chain_quests([])
            return
        quests = self._uow.quests.get_by_chain(chain_id) if self._uow else []
        self._general_tab.set_chain_quests(quests, current_id=self._current_quest_id)

    # ── Quests ──

    def _region_name(self, region_id: str) -> str:
        region = next((r for r in self._regions if r.get("id") == region_id), None)
        return region.get("name", "") if region else ""

    def _region_id_by_name(self, name: str) -> str | None:
        region = next((r for r in self._regions if r.get("name") == name), None)
        return region.get("id") if region else None

    def _quest_row(self, q: dict) -> dict:
        level_min = q.get("level_req") or 1
        level_max = q.get("level_max") or level_min
        level_txt = f"Nível {level_min}" if level_max <= level_min else f"Nível {level_min}-{level_max}"
        region_name = self._region_name(q.get("region_id") or "")
        return {
            "id": q["id"],
            "name": q.get("name") or "—",
            "subtitle": " • ".join(x for x in (region_name, level_txt) if x),
            "icon": _TYPE_ICONS.get(q.get("quest_type"), "📜"),
            "image": resolve_asset_path(self._project_dir, q.get("image_path") or ""),
            "status": q.get("status") or "Rascunho",
            "region": region_name,
            "code": q.get("code") or "",
        }

    def _refresh_quest_list_view(self):
        self._quest_list.set_records([self._quest_row(q) for q in self._quests])

    def _reload_quests(self, select_id: str | None = None):
        self._quests = self._uow.quests.get_all() if self._uow else []
        self._quests.sort(key=lambda q: (q.get("name") or ""))
        self._refresh_quest_list_view()
        self._refresh_summary()

        if select_id:
            self._on_quest_selected(select_id)
        elif self._current_quest_id and self._quest_by_id(self._current_quest_id):
            self._quest_list.select(self._current_quest_id)
        else:
            self._current_quest_id = ""
            self._set_empty()

    def _quest_by_id(self, quest_id: str) -> dict | None:
        return next((q for q in self._quests if q["id"] == quest_id), None)

    def _set_empty(self):
        self._content_title.setText("Nenhuma quest selecionada")
        self._code_lbl.setText("")
        self._status_combo.blockSignals(True)
        self._status_combo.setCurrentIndex(0)
        self._status_combo.blockSignals(False)
        self._general_tab.setEnabled(False)
        self._flow_tab.set_empty()
        self._objectives_tab.set_empty()
        self._npcs_tab.set_empty()
        self._conditions_tab.set_empty()
        self._events_tab.set_empty()
        self._scripts_tab.set_empty()
        self._notes_tab.set_empty()
        self._properties.set_empty()

    def _load_quest_into_editors(self, record: dict):
        self._content_title.setText(record.get("name") or "—")
        self._code_lbl.setText(f"ID: {record.get('code') or '—'}")
        self._status_combo.blockSignals(True)
        status = record.get("status") or "Rascunho"
        idx = self._status_combo.findText(status)
        self._status_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._status_combo.blockSignals(False)

        self._general_tab.setEnabled(True)
        chain = next((c for c in self._chains if c.get("id") == record.get("chain_id")), None)
        self._general_tab.load(record, chain_name=chain.get("name", "") if chain else "")
        self._refresh_chain_quests_preview()

        self._flow_tab.load(record)
        self._objectives_tab.load(record)
        self._conditions_tab.load(record)
        self._events_tab.load(record)
        self._scripts_tab.load(record)
        self._notes_tab.load(record)

        npc_roles = {r["role"]: r["npc_id"] for r in self._uow.quest_npcs.get_by_quest(record["id"])} if self._uow else {}
        self._npcs_tab.load(record, giver_id=npc_roles.get("giver", ""), turn_in_id=npc_roles.get("turn_in", ""))

        display = dict(record)
        display["_region_name"] = self._region_name(record.get("region_id") or "")
        display["image"] = resolve_asset_path(self._project_dir, record.get("image_path") or "")
        self._properties.load(display)

    def _on_quest_selected(self, quest_id: str):
        record = self._quest_by_id(quest_id)
        if not record:
            return
        self._current_quest_id = quest_id
        self._quest_list.select(quest_id)
        self._load_quest_into_editors(record)

    def _on_status_changed(self, status: str):
        if not self._uow or not self._current_quest_id:
            return
        self._uow.quests.update(self._current_quest_id, status=status)
        record = self._quest_by_id(self._current_quest_id)
        if record:
            record["status"] = status
        self._refresh_quest_list_view()
        self._refresh_summary()
        self._quest_list.select(self._current_quest_id)

    def _on_new_quest(self):
        if not self._uow:
            return
        quest_id = str(uuid.uuid4())
        self._uow.quests.create(
            id=quest_id,
            code=self._next_code("QST_", [q.get("code", "") for q in self._quests]),
            name="Nova Quest", title="", status="Rascunho",
            quest_type=QUEST_TYPES[0], level_req=1, level_max=1,
            description="", objectives="[]", rewards="{}", tags_json="[]",
        )
        self._reload_quests(select_id=quest_id)
        logger.info("Nova quest criada: id=%s", quest_id)

    def _save_quest(self):
        if not self._uow or not self._current_quest_id:
            return
        values = self._properties.collect()
        region_name = values.pop("_region_name", "")
        values["region_id"] = self._region_id_by_name(region_name) if region_name else None
        if values.get("image"):
            values["image_path"] = import_asset(
                self._project_dir, values.pop("image"), "assets/quests", self._current_quest_id)
        else:
            values.pop("image", None)

        general_values = self._general_tab.collect()
        chain_name = general_values.pop("_chain_name", "")
        if chain_name:
            chain = self._chain_by_name(chain_name)
            if not chain:
                chain_id = self._uow.quest_chains.create(name=chain_name)
                self._reload_chains()
            else:
                chain_id = chain["id"]
            general_values["chain_id"] = chain_id
        else:
            general_values["chain_id"] = None
        values.update(general_values)
        values.update(self._flow_tab.collect())
        values.update(self._objectives_tab.collect())
        values.update(self._conditions_tab.collect())
        values.update(self._events_tab.collect())
        values.update(self._scripts_tab.collect())
        values.update(self._notes_tab.collect())

        npc_values = self._npcs_tab.collect()
        giver_id = npc_values.pop("_giver_id", "")
        turn_in_id = npc_values.pop("_turn_in_id", "")
        values.update(npc_values)
        self._uow.quest_npcs.set_role(self._current_quest_id, giver_id or None, "giver")
        self._uow.quest_npcs.set_role(self._current_quest_id, turn_in_id or None, "turn_in")

        self._uow.quests.update(self._current_quest_id, **values)
        record = self._quest_by_id(self._current_quest_id)
        if record:
            record.update(values)
        self._refresh_quest_list_view()
        self._refresh_summary()
        self._quest_list.select(self._current_quest_id)
        self._refresh_chain_quests_preview()

    def _flush_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_quest()

    def flush_pending_saves(self):
        """Chamado pelo MenuViewMediator antes de trocar/fechar o painel —
        evita perder uma edição debounced em andamento (mesmo motivo de
        ItemsSkillsPanel.flush_pending_saves)."""
        self._flush_save()

    def _on_close_clicked(self):
        self.flush_pending_saves()
        self.closed.emit()

    # ─── Public API — jump straight to a specific quest, e.g. from a Lore
    # "@" mention click (see MenuViewMediator._on_lore_mention_open) ───

    def select_quest(self, quest_id: str):
        self._on_quest_selected(quest_id)

    def _on_quest_image_dropped(self, quest_id: str, path: str):
        if not self._uow:
            return
        relative = import_asset(self._project_dir, path, "assets/quests", quest_id)
        self._uow.quests.update(quest_id, image_path=relative)
        self._reload_quests()

    def _on_quest_delete(self, quest_id: str):
        if not self._uow:
            return
        if self._current_quest_id == quest_id:
            self._save_timer.stop()
        self._uow.quests.delete(quest_id)
        if self._current_quest_id == quest_id:
            self._current_quest_id = ""
        self._reload_quests()
        logger.info("Quest excluída: id=%s", quest_id)

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
