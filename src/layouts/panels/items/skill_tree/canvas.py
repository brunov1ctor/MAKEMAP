"""SkillTreeCanvas — the ÁRVORE DE HABILIDADES right column of the
Habilidades row.

A node graph on a QGraphicsView: browser-style tabs across the top (one
chip per guia, a "✕" to fechar a ativa, um "+" no final), rectangular
card nodes — a square showing the skill's own image (ou o ícone, se não
tiver imagem) + name + rank (3/5), com um leve brilho ao passar o mouse —
conexões desenhadas como setas (com uma luz percorrendo a extensão delas,
pra dar ideia de fluxo src → dst) entre os cards, zoom controls bottom-right.

Interações que substituem o antigo combo "Evoluir de:" do Editor de
Habilidade:
  - "+" na barra de abas abre um painel de criação (troca de página com o
    canvas, mesmo padrão do CategoryEditPanel em mobs/) pedindo o nome da
    aba, a habilidade inicial (picker de catálogo, mesma UI de "informações
    extras de mobs": `_CatalogPickerDialog`) e opcionalmente uma cor de
    tema/borda e uma cor de texto (mesma UI de duas cores + um picker
    compartilhado da criação de categoria de mob) — viram o padrão do chip
    da aba, da borda e do texto dos nós dessa guia.
  - "+ Nó" no rodapé abre o mesmo picker de habilidade pra adicionar
    qualquer outra habilidade como nó solto na aba ativa.
  - Cada card tem uma alcinha 🔗 (ícone deliberadamente diferente do "+"
    usado pra adicionar nó) — arrastar dela até outro card cria a conexão
    entre os dois; selecionar uma conexão e apertar Delete a remove.
  - Arrastar o corpo do card (fora da alça) só reposiciona, como antes.
  - Cada card tem seus PRÓPRIOS botões +/− flanqueando o "rank_current/
    rank_max" (o "0/5" que antes não tinha nenhuma UI pra editar) — cada
    habilidade ajusta o rank dela direto no próprio card, sem precisar
    selecionar nada primeiro nem passar por um painel à parte.

`_TreeStatsPanel` (stats.py) flutua sobre o canto inferior direito do
canvas (não é mais uma coluna de layout) mostrando o agregado DA ÁRVORE
INTEIRA — mini radar (Dano/Alcance/Veloc./Custo/Utilidade) somando todo nó
com rank_current > 0 na aba ativa, e o total de "Pontos gastos" (soma do
rank_current de todo nó) — estilo árvore de talentos, não é por habilidade
individual. O teto de rank (rank_max) e o dano/escalonamento de cada rank
vêm do próprio Editor de Habilidade — aba Dano, campo "Rank Máximo" + a
tabela por rank (ver skill_editor.py) — não são mais fixos em 5/iguais pra
toda habilidade.

The whole graph for the active tab (nodes, edges, and the tab's theme
colors) is persisted as one JSON document per element in the skill_trees
table (see migration 12) — theme_color/text_color live inside that same
blob, no new DB columns. uow may be None (no project open) — then it
degrades to in-memory only.

Module layout of this package (kept small on purpose — see each file's own
docstring for why it doesn't need to import its siblings back):
  - items.py       — scene-space graphics items (_NodeItem, _EdgeItem, _ConnectPreviewItem)
  - view.py         — _TreeView (the QGraphicsView) + the stats overlay anchor
  - stats.py        — _MiniRadar + _TreeStatsPanel (the floating aggregate readout)
  - tab_creator.py  — _TreeTabCreatePanel (the "+ Nova aba" page)
  - canvas.py (here) — SkillTreeCanvas, the orchestrator wiring all of the above
    to the DB (uow.skill_trees) and to the rest of the Habilidades panel.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QGraphicsScene, QSizePolicy, QFrame, QStackedWidget,
)
from PySide6.QtCore import Qt, QPointF, QTimer

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_color
from src.layouts.panels.mobs.edit_widgets import _CatalogPickerDialog
from src.layouts.panels.items.constants import panel_frame_style, sub_header, SKILL_FLAGS

from .items import _parse_json_dict, _NodeItem, _EdgeItem, _ConnectPreviewItem
from .view import _TreeView
from .stats import _TreeStatsPanel
from .tab_creator import _TreeTabCreatePanel

logger = logging.getLogger("MAKEMAP")


class SkillTreeCanvas(QWidget):
    """The whole right column: browser-style tabs, the node view and zoom
    controls, plus the "+ Nova aba" create page swapped in over it."""

    def __init__(self, uow=None, skills_provider=None, catalog_provider=None, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._skills_provider = skills_provider or (lambda: [])
        self._catalog_provider = catalog_provider or (lambda: [])
        self._trees: list[dict] = []
        self._active_key: str = ""
        self._nodes: dict[str, _NodeItem] = {}
        self._edges: list[_EdgeItem] = []
        self._selected_node: _NodeItem | None = None
        self._connecting_from: _NodeItem | None = None
        self._temp_edge_line: "_ConnectPreviewItem | None" = None
        self._zoom = 1.0
        self._active_theme_color = ""  # active tree's node border/chip theme, if set
        self._active_text_color = ""   # active tree's node name/rank text color, if set

        # Drives the small light travelling along each edge (see
        # _EdgeItem._draw_flow_light) — only runs while the canvas is
        # actually visible (see showEvent/hideEvent below).
        self._flow_phase = 0.0
        self._flow_timer = QTimer(self)
        self._flow_timer.timeout.connect(self._advance_flow)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        outer_wrap = QVBoxLayout(self)
        outer_wrap.setContentsMargins(0, 0, 0, 0)
        outer_wrap.addWidget(frame)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 12)
        frame_layout.setSpacing(8)

        self._stack = QStackedWidget()
        frame_layout.addWidget(self._stack)

        self._stack.addWidget(self._build_browse_page())

        self._tab_creator = _TreeTabCreatePanel()
        self._tab_creator.set_catalog_provider(lambda: self._catalog_provider())
        self._tab_creator.save_requested.connect(self._on_tab_creator_save)
        self._tab_creator.close_requested.connect(self._on_tab_creator_close)
        self._stack.addWidget(self._tab_creator)

    def showEvent(self, event):
        super().showEvent(event)
        self._flow_timer.start(40)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._flow_timer.stop()

    def _advance_flow(self):
        self._flow_phase = (self._flow_phase + 0.012) % 1.0
        for e in self._edges:
            e.update()
        for n in self._nodes.values():
            n.update()  # drives the card's "alive" breathing ring

    # ── UI: browse page (tabs + view + footer) ──

    def _build_browse_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        outer.addWidget(sub_header("Árvore de Habilidades"))

        # ── Browser-style tab row: one chip per guia + a trailing "+" ──
        self._tabs_row = QHBoxLayout()
        self._tabs_row.setSpacing(2)
        outer.addLayout(self._tabs_row)

        self._empty_hint = QLabel("Nenhuma guia ainda — clique em “+” para criar uma.")
        self._empty_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-style: italic; background: transparent; border: none;")
        outer.addWidget(self._empty_hint)

        # ── Graphics view ──
        view_row = QHBoxLayout()
        view_row.setSpacing(8)
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-1000, -1000, 2000, 2000)
        self._view = _TreeView(self)
        view_row.addWidget(self._view, 1)

        # Floating overlay pinned to the canvas viewport's bottom-right
        # corner (see _TreeView.set_stats_overlay) — costs the node graph
        # zero layout width, unlike a reserved sidebar column. The whole
        # active tab's aggregate stats; per-node rank +/- lives on each
        # card now (see _NodeItem).
        self._tree_stats_panel = _TreeStatsPanel()
        self._view.set_stats_overlay(self._tree_stats_panel)
        outer.addLayout(view_row, 1)

        # ── Footer: "+ Nó" (left) + hints + zoom (right) ──
        footer = QHBoxLayout()
        self._add_node_btn = QToolButton()
        self._add_node_btn.setText("+ Nó")
        self._add_node_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_node_btn.setToolTip("Adicionar outra habilidade como nó nesta guia")
        self._add_node_btn.setStyleSheet(f"""
            QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT}; border-radius: 4px; padding: 2px 8px; font-size: 9px; font-weight: bold; }}
            QToolButton:hover {{ background: {Colors.ACCENT_DIM}; }}
            QToolButton:disabled {{ color: {Colors.TEXT_MUTED}; border-color: {Colors.BORDER_SUBTLE}; background: transparent; }}
        """)
        self._add_node_btn.clicked.connect(self._on_add_node_clicked)
        footer.addWidget(self._add_node_btn)

        hints = QLabel("Arraste o card pra mover • +/− ajusta o rank • alça 🔗 conecta • Del remove a conexão selecionada")
        hints.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; background: transparent; border: none;")
        # Don't let this long line dictate the column's minimum width (it would
        # break the 2×3 grid alignment) — it can clip if the column is narrow.
        hints.setMinimumWidth(1)
        hints.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(hints)
        footer.addStretch()
        for text, cb in [("－", lambda: self.zoom_by(1 / 1.15)),
                         (None, None),
                         ("＋", lambda: self.zoom_by(1.15)),
                         ("⤢", self._reset_zoom)]:
            if text is None:
                self._zoom_lbl = QLabel("100%")
                self._zoom_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
                self._zoom_lbl.setFixedWidth(38)
                self._zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                footer.addWidget(self._zoom_lbl)
                continue
            b = QToolButton()
            b.setText(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QToolButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; font-size: 11px;
                    min-width: 22px; min-height: 20px; }}
                QToolButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            """)
            b.clicked.connect(cb)
            footer.addWidget(b)
        outer.addLayout(footer)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return page

    # ── public entry ──

    def reload(self):
        """(Re)load every guia + the active one's nodes from the DB."""
        self._trees = self._load_trees()
        if not self._active_key or self._active_key not in {t["tree_key"] for t in self._trees}:
            self._active_key = self._trees[0]["tree_key"] if self._trees else ""
        self._refresh_tab_bar()
        self._load_active_tree()

    def create_tab_for_skill(self, skill: dict, tab_name: str, theme_color: str = "", text_color: str = "") -> str:
        """Cria (ou reaproveita, se o nome já existir) uma aba com esse nome
        e a deixa ativa, com um nó raiz pra `skill` — chamado pelo painel de
        criação de aba ("+" na barra de abas) depois que o usuário escolhe a
        habilidade inicial no picker de catálogo. O ícone do nó vem do
        próprio ícone da habilidade. `theme_color`/`text_color` (escolhidos
        no mesmo painel, mesma UI de cor da criação de categoria de mob)
        viram o tema dessa aba — borda/chip e texto dos nós — guardados
        dentro do próprio blob `data` (não são coluna do banco)."""
        tab_name = tab_name.strip() or "Nova Guia"
        key = tab_name.lower().replace(" ", "_")
        if self._uow:
            existing = self._uow.skill_trees.get_all_ordered()
            if not any(t["tree_key"] == key for t in existing):
                initial_data = json.dumps(
                    {"nodes": [], "edges": [], "theme_color": theme_color, "text_color": text_color},
                    ensure_ascii=False,
                )
                self._uow.skill_trees.upsert(
                    key, name=tab_name, icon=skill.get("icon") or "✨",
                    sort_order=len(existing), data=initial_data)
        self._active_key = key
        self.reload()
        if self._active_tree():
            self._ensure_node(skill)
            self._persist()
        return key

    def show_tab_for_skill(self, skill_id: str):
        """Troca pra guia onde a habilidade já tem nó — chamado sempre que
        ela é selecionada na lista, pra árvore "seguir" o que está sendo
        editado em vez de exigir um clique numa aba pra ver."""
        if not self._uow:
            return
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            if any(n.get("id") == skill_id for n in data.get("nodes", [])):
                if tree["tree_key"] != self._active_key:
                    self._active_key = tree["tree_key"]
                    self.reload()
                return

    @staticmethod
    def _skill_rank_max(skill: dict) -> int:
        """Rank Máximo definido no Editor de Habilidade (aba Dano — ver
        skill_editor.py._rank_max_spin), lido de dentro do `stats` JSON.
        Falls back to 5 pra habilidades salvas antes desse campo existir."""
        stats = _parse_json_dict(skill.get("stats"))
        try:
            return max(1, min(10, int(stats.get("rank_max") or 5)))
        except (TypeError, ValueError):
            return 5

    def refresh_node_metadata(self, skill_id: str, skill: dict):
        """Atualiza nome/ícone/imagem/rank-máximo de um nó já existente pra
        essa habilidade, em qualquer aba onde ela exista — chamado ao salvar
        a habilidade no editor (mudar "Rank Máximo" lá se reflete aqui,
        inclusive baixando rank_current de nós que já tinham investido mais
        pontos do que o novo teto permite). Não cria nó nenhum (isso só
        acontece via "+ Nova aba"/"+ Nó"/arrastar a alça, direto no canvas)."""
        rank_max = self._skill_rank_max(skill)
        if not self._uow:
            node = self._nodes.get(skill_id)
            if node:
                node.name = skill.get("name", node.name)
                node.icon = skill.get("icon") or node.icon
                node.set_image_path(skill.get("image_path") or node.image_path)
                node.rank_max = rank_max
                node.rank_current = min(node.rank_current, rank_max)
                node.update()
            return
        touched_active = False
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            nodes = data.get("nodes", [])
            target = next((n for n in nodes if n.get("id") == skill_id), None)
            if not target:
                continue
            target["name"] = skill.get("name", target.get("name"))
            target["icon"] = skill.get("icon") or target.get("icon")
            target["image_path"] = skill.get("image_path") or target.get("image_path", "")
            target["rank_max"] = rank_max
            target["rank_current"] = min(int(target.get("rank_current", 0)), rank_max)
            self._uow.skill_trees.upsert(tree["tree_key"], data=json.dumps(data, ensure_ascii=False))
            if tree["tree_key"] == self._active_key:
                touched_active = True
        if touched_active:
            node = self._nodes.get(skill_id)
            if node:
                node.name = skill.get("name", node.name)
                node.icon = skill.get("icon") or node.icon
                node.set_image_path(skill.get("image_path") or node.image_path)
                node.rank_max = rank_max
                node.rank_current = min(node.rank_current, rank_max)
                node.update()
                self._refresh_tree_stats()

    def remove_skill_node(self, skill_id: str):
        """Chamado pelo painel ao excluir uma habilidade — tira o nó dela
        (e qualquer conexão que o referencie) de qualquer guia onde exista,
        pra não sobrar um nó órfão apontando pra um id que já era."""
        if not self._uow:
            return
        for tree in self._uow.skill_trees.get_all_ordered():
            data = self._parse_data(tree.get("data"))
            nodes = data.get("nodes", [])
            if not any(n.get("id") == skill_id for n in nodes):
                continue
            data["nodes"] = [n for n in nodes if n.get("id") != skill_id]
            data["edges"] = [e for e in data.get("edges", []) if skill_id not in e]
            self._uow.skill_trees.upsert(tree["tree_key"], data=json.dumps(data, ensure_ascii=False))
            if tree["tree_key"] == self._active_key:
                self._load_active_tree()

    def _ensure_node(self, skill: dict) -> _NodeItem:
        """Nó existente pro id, ou um novo posicionado perto do centro da
        vista (deslocado a cada novo nó pra não empilhar em cima). O teto de
        rank vem do próprio "Rank Máximo" definido na habilidade (Editor de
        Habilidade, aba Dano) — não mais um 5 fixo pra toda habilidade."""
        existing = self._nodes.get(skill.get("id"))
        if existing:
            existing.name = skill.get("name", existing.name)
            existing.icon = skill.get("icon") or existing.icon
            existing.set_image_path(skill.get("image_path") or existing.image_path)
            return existing
        # `skill` aqui costuma ser uma row do catálogo (id/name/icon/rarity/
        # image_path) sem o `stats` JSON completo — resolve o registro cheio
        # pra ler o Rank Máximo real da habilidade.
        full = next((sk for sk in (self._skills_provider() or []) if sk.get("id") == skill.get("id")), None)
        rank_max = self._skill_rank_max(full or skill)
        center = self._view.mapToScene(self._view.viewport().rect().center())
        offset = (len(self._nodes) % 5) * 24
        data = {
            "id": skill["id"],
            "name": skill.get("name", "Habilidade"),
            "icon": skill.get("icon") or "✨",
            "image_path": skill.get("image_path") or "",
            "color": item_rarity_color(skill.get("rarity", "common")),
            "x": center.x() + offset, "y": center.y() + offset,
            "rank_current": 0, "rank_max": rank_max,
        }
        return self._add_node_item(data)

    def _load_trees(self) -> list[dict]:
        if not self._uow:
            return []
        return self._uow.skill_trees.get_all_ordered()

    # ── tab bar ──

    def _refresh_tab_bar(self):
        while self._tabs_row.count():
            item = self._tabs_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for tree in self._trees:
            self._tabs_row.addWidget(self._make_tab_chip(tree))
        self._tabs_row.addWidget(self._make_new_tab_chip())
        self._tabs_row.addStretch()
        self._empty_hint.setVisible(not self._trees)
        self._add_node_btn.setEnabled(self._active_tree() is not None)

    def _make_tab_chip(self, tree: dict) -> QWidget:
        chip = QWidget()
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        active = tree["tree_key"] == self._active_key
        # The tab's own theme color (chosen at creation, see
        # _TreeTabCreatePanel) drives the chip's active-state accent when
        # set — falls back to the app-wide accent otherwise.
        theme_color = self._parse_data(tree.get("data")).get("theme_color") or ""
        accent = theme_color or Colors.ACCENT
        btn = QToolButton()
        btn.setText(f"{tree.get('icon', '')} {tree['name']}".strip())
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {Colors.TEXT_MUTED};
                border: none; border-bottom: 2px solid transparent;
                padding: 4px 8px; font-size: 9px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.TEXT_SECONDARY}; }}
            QToolButton:checked {{ color: {accent}; border-bottom: 2px solid {accent}; }}
        """)
        btn.clicked.connect(lambda _c=False, key=tree["tree_key"]: self._switch_active_tab(key))
        lay.addWidget(btn)
        if active:
            close_btn = QToolButton()
            close_btn.setText("✕")
            close_btn.setFixedSize(14, 14)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setToolTip("Excluir esta guia")
            close_btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 9px; }}
                QToolButton:hover {{ color: {Colors.ERROR}; }}
            """)
            close_btn.clicked.connect(lambda _c=False, key=tree["tree_key"]: self._delete_tab(key))
            lay.addWidget(close_btn)
        return chip

    def _make_new_tab_chip(self) -> QToolButton:
        btn = QToolButton()
        btn.setText("+")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Nova aba")
        btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; color: {Colors.ACCENT}; border: none;
                padding: 4px 8px; font-size: 11px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        btn.clicked.connect(self._open_tab_creator)
        return btn

    def _switch_active_tab(self, key: str):
        if key == self._active_key:
            return
        self._active_key = key
        self.reload()

    def _delete_tab(self, key: str):
        """Exclui a guia direto no clique do "✕" do chip — sem QMessageBox
        (isso abriria uma janela nativa fora do app; mesmo no-confirm
        precedent do "⋮" das categorias de mob, ver panel_category_mixin.py's
        _on_delete_category)."""
        tree = next((t for t in self._trees if t["tree_key"] == key), None)
        if not tree:
            return
        if self._uow:
            self._uow.skill_trees.delete_tree(key)
        if self._active_key == key:
            self._active_key = ""
        self.reload()
        logger.info("Guia da árvore de habilidades excluída: %s", key)

    # ── tab creator page ──

    def _open_tab_creator(self):
        self._tab_creator.load()
        self._stack.setCurrentIndex(1)

    def _on_tab_creator_save(self, name: str, skill: dict, theme_color: str, text_color: str):
        self.create_tab_for_skill(skill, name, theme_color=theme_color, text_color=text_color)
        self._stack.setCurrentIndex(0)

    def _on_tab_creator_close(self):
        self._stack.setCurrentIndex(0)

    # ── "+ Nó" ──

    def _on_add_node_clicked(self):
        if not self._active_tree():
            return
        dlg = _CatalogPickerDialog("Vincular Habilidade", "Buscar habilidade", self._catalog_provider(), parent=self._view)
        picked_id = dlg.exec()
        if not picked_id:
            return
        skill = next((sk for sk in self._catalog_provider() if sk.get("id") == picked_id), None)
        if not skill:
            return
        self._ensure_node(skill)
        self._persist()

    # ── scene <-> data ──

    def _active_tree(self) -> dict | None:
        for t in self._trees:
            if t["tree_key"] == self._active_key:
                return t
        return None

    def _load_active_tree(self):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._selected_node = None
        tree = self._active_tree()
        if not tree:
            self._active_theme_color = ""
            self._active_text_color = ""
            self._refresh_tree_stats()
            return
        data = self._parse_data(tree.get("data"))
        self._active_theme_color = data.get("theme_color") or ""
        self._active_text_color = data.get("text_color") or ""
        for nd in data.get("nodes", []):
            self._add_node_item(nd)
        for edge in data.get("edges", []):
            src = self._nodes.get(edge[0])
            dst = self._nodes.get(edge[1])
            if src and dst:
                self._add_edge_item(src, dst)
        self._refresh_tree_stats()

    def _add_node_item(self, data: dict) -> _NodeItem:
        node = _NodeItem(data, self)
        node.clicked.connect(self._on_node_clicked)
        node.moved.connect(lambda n: self._persist())
        self._scene.addItem(node)
        self._nodes[node.node_id] = node
        return node

    def _add_edge_item(self, src: _NodeItem, dst: _NodeItem) -> _EdgeItem:
        edge = _EdgeItem(src, dst, self)
        self._scene.addItem(edge)
        self._edges.append(edge)
        return edge

    # ── connecting nodes by dragging a node's handle ──

    def _begin_connect(self, node: _NodeItem, scene_pos: QPointF):
        # Defensive: a stale preview from an unfinished previous drag (see
        # _TreeView.mousePressEvent/mouseReleaseEvent's cleanup) must not
        # leak when a fresh connect starts.
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        self._connecting_from = node
        preview = _ConnectPreviewItem(node.center(), scene_pos, self)
        self._scene.addItem(preview)
        self._temp_edge_line = preview

    def _update_connect(self, scene_pos: QPointF):
        if self._connecting_from and self._temp_edge_line:
            self._temp_edge_line.set_end(scene_pos)

    def _finish_connect(self, scene_pos: QPointF):
        src = self._connecting_from
        self._connecting_from = None
        if self._temp_edge_line:
            self._scene.removeItem(self._temp_edge_line)
            self._temp_edge_line = None
        if not src:
            return
        dst = next(
            (n for n in self._nodes.values() if n is not src and n.sceneBoundingRect().contains(scene_pos)),
            None,
        )
        if dst and not self._edge_exists(src, dst):
            self._add_edge_item(src, dst)
            self._persist()

    def _delete_selected_edges(self):
        selected = [e for e in self._edges if e.isSelected()]
        if not selected:
            return
        for e in selected:
            self._scene.removeItem(e)
            self._edges.remove(e)
        self._persist()

    # ── interaction ──

    def _on_node_clicked(self, node: _NodeItem, modifiers):
        self._select_node(node)

    def _select_node(self, node: _NodeItem | None):
        for e in self._edges:
            e.setSelected(False)
        if self._selected_node and self._selected_node is not node:
            self._selected_node.set_selected(False)
        self._selected_node = node
        if node:
            node.set_selected(True)

    # ── tree-wide stats panel + per-node rank ──

    def _skill_metrics_for(self, node: _NodeItem) -> dict:
        """Resolves the full skill record behind a node (name/icon alone
        don't carry cooldown/mana_cost/rank_damage) and reads the ranked
        Dano Base/Escalonamento for the node's CURRENT rank (falls back to
        rank 1's row as a preview when rank_current is still 0)."""
        full = next((sk for sk in (self._skills_provider() or []) if sk.get("id") == node.node_id), None)
        if not full:
            return {}
        stats = _parse_json_dict(full.get("stats"))
        rank_damage = stats.get("rank_damage") or []
        idx = max(0, node.rank_current - 1)
        entry = rank_damage[idx] if idx < len(rank_damage) else {}
        flags_on = sum(1 for key, _label, default in SKILL_FLAGS if stats.get(key, default))
        return {
            "dano_base": entry.get("dano_base", 0),
            "escalonamento": entry.get("escalonamento", 0),
            "alcance": stats.get("alcance", 0),
            "cooldown": full.get("cooldown", 0),
            "mana_cost": full.get("mana_cost", 0),
            "flags_on": flags_on,
            "flags_total": len(SKILL_FLAGS),
        }

    def _refresh_tree_stats(self):
        """Aggregates every node with rank_current > 0 (actually invested)
        in the active tab into the sidebar panel — the whole build's
        totals, not any single node's. Called after anything that can
        change a node's rank/existence (see _persist()/_load_active_tree)."""
        points_spent = sum(n.rank_current for n in self._nodes.values())
        active_nodes = [n for n in self._nodes.values() if n.rank_current > 0]
        if not active_nodes:
            self._tree_stats_panel.set_empty(points_spent)
            return
        total_dano, max_alcance, total_mana = 0.0, 0.0, 0.0
        speed_scores, flag_fracs = [], []
        for node in active_nodes:
            m = self._skill_metrics_for(node)
            total_dano += float(m.get("dano_base", 0))
            max_alcance = max(max_alcance, float(m.get("alcance", 0)))
            total_mana += float(m.get("mana_cost", 0))
            cooldown = float(m.get("cooldown", 0))
            speed_scores.append(1.0 if cooldown <= 0 else max(0.0, 1 - min(cooldown, 10) / 10))
            flags_total = max(1, m.get("flags_total", 1))
            flag_fracs.append(m.get("flags_on", 0) / flags_total)
        self._tree_stats_panel.set_stats(
            dano_total=total_dano, alcance=max_alcance, mana_total=total_mana,
            speed=sum(speed_scores) / len(speed_scores), util=sum(flag_fracs) / len(flag_fracs),
            points_spent=points_spent, node_count=len(active_nodes),
        )

    def _adjust_node_rank(self, node: _NodeItem, delta: int):
        """Called by the +/- hit-targets drawn directly on the node's own
        card (see _NodeItem._rank_button_rects/mousePressEvent) — each card
        manages its own rank independently, no need to select it first."""
        new_rank = max(0, min(node.rank_max, node.rank_current + delta))
        if new_rank == node.rank_current:
            return
        node.rank_current = new_rank
        node.update()
        self._persist()
        self._refresh_tree_stats()

    def _edge_exists(self, a: _NodeItem, b: _NodeItem) -> bool:
        return any((e.src is a and e.dst is b) or (e.src is b and e.dst is a) for e in self._edges)

    def _on_node_moving(self, node: _NodeItem):
        for e in self._edges:
            if e.src is node or e.dst is node:
                e.update_path()

    # ── zoom ──

    def zoom_by(self, factor: float):
        new_zoom = self._zoom * factor
        if not (0.3 <= new_zoom <= 3.0):
            return
        self._zoom = new_zoom
        self._view.scale(factor, factor)
        self._zoom_lbl.setText(f"{int(self._zoom * 100)}%")

    def _reset_zoom(self):
        if self._zoom != 1.0:
            self._view.scale(1 / self._zoom, 1 / self._zoom)
            self._zoom = 1.0
            self._zoom_lbl.setText("100%")
        self._view.centerOn(0, 0)

    # ── persistence ──

    def _persist(self):
        tree = self._active_tree()
        if not tree:
            return
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [[e.src.node_id, e.dst.node_id] for e in self._edges],
            # Preserved as-is — this is the only writer of this tree's data
            # blob, and it must not clobber the theme chosen at tab
            # creation (see create_tab_for_skill) on every node move/connect.
            "theme_color": self._active_theme_color,
            "text_color": self._active_text_color,
        }
        tree["data"] = json.dumps(data, ensure_ascii=False)
        if self._uow:
            self._uow.skill_trees.upsert(self._active_key, data=tree["data"])

    @staticmethod
    def _parse_data(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {"nodes": [], "edges": []}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"nodes": [], "edges": []}
        except (json.JSONDecodeError, TypeError):
            return {"nodes": [], "edges": []}
