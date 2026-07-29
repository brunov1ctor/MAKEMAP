"""ItemsSkillsPanel — the fullscreen "Itens e Habilidades" module.

Two stacked halves inside a vertical splitter, so dragging the divider
trades height between them (responsive between each other):

    ┌──────────── Itens ────────────┐
    │  lista │ editor │ prévia+info  │   (horizontal splitter)
    ├──────── Habilidades ──────────┤
    │  lista │ editor │ árvore        │   (horizontal splitter)
    └───────────────────────────────┘

Column widths and the row split are ratio-based and recomputed on every
window resize (see _apply_responsive_layout) so the whole thing keeps the
reference's proportions as the monitor size changes — until the user drags a
handle themselves, after which that splitter is left alone (same nudge-vs-
drag heuristic MobsPanel uses).
"""

from __future__ import annotations

import json
import logging
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton, QFrame,
    QSizePolicy, QSplitter, QStackedWidget, QMenu, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors
from src.services.project_assets import import_asset, resolve_asset_path
from src.layouts.panels.mobs.categories import item_rarity_color
from src.layouts.panels.items.constants import (
    ITEM_CATEGORY_NAMES, SKILL_CATEGORIES,
    category_display, rarity_options,
    skill_tier_options, skill_tier_label, skill_tier_color,
)
from src.layouts.panels.items.import_export_constants import (
    _ITEM_DB_COLUMNS, _ITEM_JSON_FIELDS, _ITEM_BOOL_FIELDS,
    _SKILL_DB_COLUMNS, _SKILL_JSON_FIELDS, _SKILL_BOOL_FIELDS,
    coerce_import_stats,
)
from src.layouts.panels.items.entity_list import EntityListColumn
from src.layouts.panels.items.item_editor import ItemEditor
from src.layouts.panels.items.item_preview import ItemPreview
from src.layouts.panels.items.skill_editor import SkillEditor
from src.layouts.panels.items.skill_tree import SkillTreeCanvas
from src.layouts.panels.items.panel_import_export_mixin import ItemsImportExportMixin

logger = logging.getLogger("MAKEMAP")

# Emoji shown in the list column per category, so a row reads at a glance
# without needing each record to carry an image.
_ITEM_CAT_ICONS = {
    "Arma": "🗡", "Armadura": "🛡", "Consumível": "🧪", "Material": "⛏",
    "Receita": "📜", "Missão": "🗝", "Outro": "📦",
}


class ItemsSkillsPanel(ItemsImportExportMixin, QWidget):
    """Fullscreen Itens e Habilidades module."""

    closed = Signal()

    # Column ratios (lista / editor / direita) and the row split, tuned to
    # the reference's roughly-even thirds and 50/50 stack.
    _COL_RATIOS = (0.31, 0.37, 0.32)
    _ROW_RATIOS = (0.52, 0.48)
    _NUDGE = 6

    def __init__(self, uow, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._items: list[dict] = []
        self._skills: list[dict] = []
        self._skill_catalog_rows: list[dict] = []  # resolved-image_path rows, feeds the tree's catalog pickers
        self._current_item_id = ""
        self._current_skill_id = ""
        self._user_dragged: set[int] = set()  # ids() of splitters the user adjusted
        self._auto_positions: dict[int, dict[int, int]] = {}
        self._syncing = False  # guards the column-splitter mirror against recursion

        # ItemsImportExportMixin state
        self._tools_mode: str | None = None
        self._import_entity_mode: str = "item"
        self._staged_image_folder: str = ""
        self._staged_image_files: dict[str, str] = {}
        self._template_fmt: str = "json"

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Debounced save timers — one per editor, so a burst of keystrokes
        # collapses into a single UPDATE.
        self._item_save_timer = QTimer(self)
        self._item_save_timer.setSingleShot(True)
        self._item_save_timer.setInterval(400)
        self._item_save_timer.timeout.connect(self._save_item)
        self._skill_save_timer = QTimer(self)
        self._skill_save_timer.setSingleShot(True)
        self._skill_save_timer.setInterval(400)
        self._skill_save_timer.timeout.connect(self._save_skill)

        self._build_ui()
        self._reload_items()
        self._reload_skills()
        self._skill_tree.reload()
        self._apply_responsive_layout()

    # ── UI ──

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 16)
        outer.setSpacing(8)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel("⚔")
        icon.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header.addWidget(icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("ITENS E HABILIDADES")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14pt; font-weight: bold; background: transparent; border: none;")
        subtitle = QLabel("Catalogue armas, itens, habilidades e monte árvores de progressão.")
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

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none; font-size: 14px; border-radius: 14px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self._on_close_clicked)
        header.addWidget(close_btn)
        outer.addLayout(header)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.GLASS_BORDER}; border: none;")
        outer.addWidget(sep)

        # ── Itens row ──
        rarity_labels = [label for _key, label in rarity_options()]
        self._item_list = EntityListColumn(
            "Itens", "+ Novo Item",
            filters=[("Todas as Categorias", ITEM_CATEGORY_NAMES), ("Todas as Raridades", rarity_labels)],
        )
        self._item_list.new_requested.connect(self._on_new_item)
        self._item_list.selected.connect(self._on_item_selected)
        self._item_list.delete_requested.connect(self._on_item_delete)
        self._item_editor = ItemEditor()
        self._item_editor.changed.connect(self._item_save_timer.start)
        self._item_preview = ItemPreview()
        self._item_preview.image_dropped.connect(self._item_editor._on_image_set)

        self._items_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._items_splitter.setChildrenCollapsible(False)
        self._items_splitter.setHandleWidth(8)
        self._items_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        self._items_splitter.addWidget(self._item_list)
        self._items_splitter.addWidget(self._item_editor)
        self._items_splitter.addWidget(self._item_preview)
        self._items_splitter.splitterMoved.connect(lambda p, i: self._on_splitter_moved(self._items_splitter, p, i))

        # ── Habilidades row ──
        # "Tier" no lugar de "Raridade" — habilidade não tem raridade de
        # loot, tem progressão (Inicial/Intermediário/.../Lendário). Mesmas
        # chaves da escala de raridade dos itens por trás (ver
        # constants.SKILL_TIER_DEFS), só com rótulo/coluna próprios.
        tier_labels = [label for _key, label in skill_tier_options()]
        self._skill_list = EntityListColumn(
            "Habilidades", "+ Nova Habilidade",
            filters=[("Todas as Categorias", SKILL_CATEGORIES), ("Todos os Tiers", tier_labels)],
            rarity_header="Tier", rarity_label_fn=skill_tier_label, rarity_color_fn=skill_tier_color,
        )
        self._skill_list.new_requested.connect(self._on_new_skill)
        self._skill_list.selected.connect(self._on_skill_selected)
        self._skill_list.delete_requested.connect(self._on_skill_delete)
        self._skill_editor = SkillEditor(skills_provider=lambda: self._skills, items_provider=lambda: self._items)
        self._skill_editor.changed.connect(self._skill_save_timer.start)
        self._skill_tree = SkillTreeCanvas(
            self._uow, skills_provider=lambda: self._skills,
            catalog_provider=lambda: self._skill_catalog_rows,
            project_dir=self._project_dir,
        )

        self._skills_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._skills_splitter.setChildrenCollapsible(False)
        self._skills_splitter.setHandleWidth(8)
        self._skills_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        self._skills_splitter.addWidget(self._skill_list)
        self._skills_splitter.addWidget(self._skill_editor)
        self._skills_splitter.addWidget(self._skill_tree)
        self._skills_splitter.splitterMoved.connect(lambda p, i: self._on_splitter_moved(self._skills_splitter, p, i))

        # Equal per-column minimum widths on both rows, so setSizes() gives
        # identical actual widths in each row → the three vertical dividers
        # line up (the "H") instead of drifting apart under differing content.
        for w in (self._item_list, self._skill_list):
            w.setMinimumWidth(230)
        for w in (self._item_editor, self._skill_editor):
            w.setMinimumWidth(300)
        for w in (self._item_preview, self._skill_tree):
            w.setMinimumWidth(250)

        # ── Vertical stack ──
        self._rows_splitter = QSplitter(Qt.Orientation.Vertical)
        # Collapsible=True aqui (diferente dos splitters de coluna acima) —
        # arrastar o divisor até o topo ou o fim esconde Itens ou
        # Habilidades por completo, em vez de parar na largura mínima de
        # cada linha.
        self._rows_splitter.setChildrenCollapsible(True)
        self._rows_splitter.setHandleWidth(8)
        self._rows_splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        self._rows_splitter.addWidget(self._items_splitter)
        self._rows_splitter.addWidget(self._skills_splitter)
        self._rows_splitter.splitterMoved.connect(lambda p, i: self._on_splitter_moved(self._rows_splitter, p, i))

        # ── Body stack: normal Itens/Habilidades view vs. the Importar/
        # Exportar tools panel (see ItemsImportExportMixin) — the module
        # has no spare column to take over like MobsPanel's right column,
        # so Importar/Exportar swap the whole body instead. ──
        self._body_stack = QStackedWidget()
        self._body_stack.addWidget(self._rows_splitter)
        self._body_stack.addWidget(self._build_tools_panel())
        outer.addWidget(self._body_stack, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _on_splitter_moved(self, splitter: QSplitter, pos: int, index: int):
        if self._syncing:
            return
        expected = self._auto_positions.get(id(splitter), {}).get(index)
        if expected is not None and abs(pos - expected) < self._NUDGE:
            return
        # The two column splitters are locked together to form one 2×3 grid
        # ("H" shape): dragging a column divider in one row moves the same
        # divider in the other, and both are marked user-adjusted so the
        # responsive pass stops overriding them.
        if splitter in (self._items_splitter, self._skills_splitter):
            other = self._skills_splitter if splitter is self._items_splitter else self._items_splitter
            self._user_dragged.add(id(self._items_splitter))
            self._user_dragged.add(id(self._skills_splitter))
            self._sync_columns(source=splitter, target=other)
        else:
            self._user_dragged.add(id(splitter))

    def _sync_columns(self, source: QSplitter, target: QSplitter):
        """Copy `source`'s column widths onto `target` so the vertical
        dividers stay aligned across both rows."""
        self._syncing = True
        try:
            target.setSizes(source.sizes())
        finally:
            self._syncing = False

    def _apply_responsive_layout(self):
        if not hasattr(self, "_rows_splitter"):
            return
        self._syncing = True
        try:
            # Both column splitters share one set of ratio-based widths, so
            # their dividers line up (the "H"). Skip if the user has taken
            # manual control of the grid.
            columns_locked = (id(self._items_splitter) in self._user_dragged
                              or id(self._skills_splitter) in self._user_dragged)
            if not columns_locked:
                w = self._items_splitter.width()
                if w > 0:
                    sizes = [max(240, round(w * r)) for r in self._COL_RATIOS]
                    sizes[-1] = max(240, w - sizes[0] - sizes[1])
                    for splitter in (self._items_splitter, self._skills_splitter):
                        splitter.setSizes(sizes)
                        self._record_auto_positions(splitter)
        finally:
            self._syncing = False
        # Vertical row split
        if id(self._rows_splitter) not in self._user_dragged:
            h = self._rows_splitter.height()
            if h > 0:
                top = max(200, round(h * self._ROW_RATIOS[0]))
                self._rows_splitter.setSizes([top, max(200, h - top)])
                self._record_auto_positions(self._rows_splitter)

    def _record_auto_positions(self, splitter: QSplitter):
        actual = splitter.sizes()
        cumulative = 0
        positions: dict[int, int] = {}
        for i in range(len(actual) - 1):
            cumulative += actual[i]
            positions[i] = cumulative
        self._auto_positions[id(splitter)] = positions

    # ── Items CRUD ──

    def _reload_items(self, select_id: str | None = None):
        self._items = self._uow.items.get_all() if self._uow else []
        rows = []
        for it in self._items:
            rows.append({
                "id": it["id"],
                "name": it.get("name", ""),
                "category": category_display(it.get("item_type"), it.get("subcategory")),
                "rarity": it.get("rarity", "common"),
                "level": it.get("level_req", 1),
                "code": it.get("code", ""),
                "icon": _ITEM_CAT_ICONS.get(it.get("item_type"), "📦"),
                "image_path": resolve_asset_path(self._project_dir, it.get("image_path") or ""),
            })
        self._item_list.set_rows(rows)
        if select_id:
            self._item_list.select(select_id)
            self._on_item_selected(select_id)
        elif not self._current_item_id:
            self._item_editor.set_empty()
            self._item_preview.update(None)

    def _item_by_id(self, item_id: str) -> dict | None:
        return next((i for i in self._items if i["id"] == item_id), None)

    def _item_display(self, record: dict) -> dict:
        """Cópia com image_path resolvido para caminho absoluto — self._items
        continua guardando o caminho relativo (o que o banco tem), para
        Exportar/Importar continuarem portáveis."""
        display = dict(record)
        display["image_path"] = resolve_asset_path(self._project_dir, record.get("image_path") or "")
        return display

    def _flush_item_save(self):
        """Commits a pending debounced edit (see _item_save_timer) before
        the selection moves elsewhere — otherwise the timer fires 400ms
        later against whatever item/skill is selected *then*, silently
        dropping the edit the user just made (e.g. picking an image and
        immediately clicking another item in the list)."""
        if self._item_save_timer.isActive():
            self._item_save_timer.stop()
            self._save_item()

    def _flush_skill_save(self):
        if self._skill_save_timer.isActive():
            self._skill_save_timer.stop()
            self._save_skill()

    def flush_pending_saves(self):
        """Called by MainLayout before it tears down this panel — whether
        the user clicked the panel's own ✕ or just navigated to another
        menu — so a debounced edit in flight (see _item_save_timer/
        _skill_save_timer) isn't silently lost."""
        self._flush_item_save()
        self._flush_skill_save()

    def _on_close_clicked(self):
        self.flush_pending_saves()
        self.closed.emit()

    def _on_item_selected(self, item_id: str):
        self._flush_item_save()
        record = self._item_by_id(item_id)
        if not record:
            return
        self._current_item_id = item_id
        display = self._item_display(record)
        self._item_editor.load(display)
        self._item_preview.update(display)

    def _on_new_item(self):
        if not self._uow:
            return
        self._flush_item_save()
        item_id = str(uuid.uuid4())
        code = self._next_code("ITM_", [i.get("code", "") for i in self._items], start=1001)
        self._uow.items.create(
            id=item_id, code=code, name="Novo Item", item_type="Arma",
            subcategory="Espada", rarity="common", level_req=1, stats="{}",
        )
        self._reload_items(select_id=item_id)
        logger.info("Novo item criado: id=%s code=%s", item_id, code)

    def _save_item(self):
        if not self._uow or not self._current_item_id:
            return
        values = self._item_editor.collect()
        if values.get("image_path"):
            values["image_path"] = import_asset(
                self._project_dir, values["image_path"], "assets/items", self._current_item_id)
        self._uow.items.update(self._current_item_id, **values)
        # refresh the in-memory record + list row + preview live
        record = self._item_by_id(self._current_item_id)
        if record:
            record.update(values)
            self._item_preview.update(self._item_display(record))
        self._reload_items()
        self._item_list.select(self._current_item_id)

    def _on_item_delete(self, item_id: str):
        if not self._uow:
            return
        if self._current_item_id == item_id:
            self._item_save_timer.stop()  # about to delete this row — discard, don't save
        record = self._item_by_id(item_id)
        name = record.get("name") if record else item_id
        reply = QMessageBox.question(
            self, "Excluir item", f'Excluir "{name}"? Essa ação não pode ser desfeita.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._uow.items.delete(item_id)
        if self._current_item_id == item_id:
            self._current_item_id = ""
        self._reload_items()
        logger.info("Item excluído: id=%s", item_id)

    # ── Skills CRUD ──

    def _reload_skills(self, select_id: str | None = None):
        self._skills = self._uow.skills.get_all() if self._uow else []
        rows = []
        for sk in self._skills:
            # O ícone vem do próprio Editor de Habilidade agora (a coluna
            # `icon` do banco), não mais de uma categoria — a lista e os
            # nós/guias criados a partir de "Evoluir de:" mostram o mesmo
            # emoji dessa forma.
            sk["icon"] = sk.get("icon") or "✨"
            rows.append({
                "id": sk["id"],
                "name": sk.get("name", ""),
                "category": sk.get("category", ""),
                "rarity": sk.get("rarity", "common"),
                "level": sk.get("level", 1),
                "code": sk.get("code", ""),
                "icon": sk["icon"],
                "image_path": resolve_asset_path(self._project_dir, sk.get("image_path") or ""),
            })
        self._skill_list.set_rows(rows)
        # Mesma lista de rows (image_path já resolvido) usada pelos pickers
        # de catálogo da Árvore de Habilidades ("+" de nova aba e "+ Nó").
        self._skill_catalog_rows = rows
        if select_id:
            self._skill_list.select(select_id)
            self._on_skill_selected(select_id)
        elif not self._current_skill_id:
            self._skill_editor.set_empty()

    def _skill_by_id(self, skill_id: str) -> dict | None:
        return next((s for s in self._skills if s["id"] == skill_id), None)

    def _on_skill_selected(self, skill_id: str):
        self._flush_skill_save()
        record = self._skill_by_id(skill_id)
        if not record:
            return
        self._current_skill_id = skill_id
        display = dict(record)
        display["image_path"] = resolve_asset_path(self._project_dir, record.get("image_path") or "")
        self._skill_editor.load(display)
        # A árvore "segue" a habilidade sendo editada — sem isso não haveria
        # mais como ver a guia onde ela mora, já que trocar de guia deixou
        # de ser um clique manual.
        self._skill_tree.show_tab_for_skill(skill_id)

    def _on_new_skill(self):
        if not self._uow:
            return
        self._flush_skill_save()
        skill_id = str(uuid.uuid4())
        code = self._next_code("SKL_", [s.get("code", "") for s in self._skills], start=1, width=3)
        # "category" não tem mais campo no editor — fica um valor interno
        # fixo, só preenchendo a coluna do banco.
        self._uow.skills.create(
            id=skill_id, code=code, name="Nova Habilidade", category="Ataque",
            rarity="common", level=1, stats="{}",
        )
        self._reload_skills(select_id=skill_id)
        logger.info("Nova habilidade criada: id=%s code=%s", skill_id, code)

    def _save_skill(self):
        if not self._uow or not self._current_skill_id:
            return
        values = self._skill_editor.collect()
        if values.get("image_path"):
            values["image_path"] = import_asset(
                self._project_dir, values["image_path"], "assets/skills", self._current_skill_id)
        self._uow.skills.update(self._current_skill_id, **values)
        record = self._skill_by_id(self._current_skill_id)
        if record:
            record.update(values)
        self._reload_skills()
        self._skill_list.select(self._current_skill_id)
        # Nome/ícone do nó (se essa habilidade já tiver um em alguma aba)
        # acompanham a edição — mas salvar não cria nó nem conexão nenhuma
        # por conta própria (isso agora é só "+ Nova aba"/"+ Nó"/arrastar a
        # alça, direto no canvas da árvore).
        if record:
            self._skill_tree.refresh_node_metadata(self._current_skill_id, record)

    def _on_skill_delete(self, skill_id: str):
        """Exclui direto no clique — sem QMessageBox (isso abriria uma
        janela nativa fora do app; mesmo no-confirm precedent do "✕" das
        guias da Árvore de Habilidades, ver skill_tree/canvas.py's
        _delete_tab). remove_skill_node tira o nó dela (e qualquer conexão
        que o referencie) de toda guia onde exista, pra não deixar a árvore
        com um nó órfão apontando pra um id que já era."""
        if not self._uow:
            return
        if self._current_skill_id == skill_id:
            self._skill_save_timer.stop()  # about to delete this row — discard, don't save
        self._uow.skills.delete(skill_id)
        self._skill_tree.remove_skill_node(skill_id)
        if self._current_skill_id == skill_id:
            self._current_skill_id = ""
        self._reload_skills()
        logger.info("Habilidade excluída: id=%s", skill_id)

    # ── JSON bulk create ──

    def _import_item_records(self, records: list[dict]) -> str | None:
        """The actual item-create loop, used by the Importar cards
        (ItemsImportExportMixin). Every key beyond _ITEM_DB_COLUMNS falls
        into the `stats` JSON blob — see import_export_constants.py for why
        that needs coerce_import_stats rather than a plain dict comprehension."""
        if not self._uow:
            return None
        existing = [i.get("code", "") for i in self._items]
        last_id = None
        for rec in records:
            if not isinstance(rec, dict) or not rec.get("name"):
                continue
            item_id = str(uuid.uuid4())
            code = self._next_code("ITM_", existing, start=1001)
            existing.append(code)
            stats_in = {k: v for k, v in rec.items() if k not in _ITEM_DB_COLUMNS}
            self._uow.items.create(
                id=item_id, code=code,
                name=str(rec.get("name") or "Novo Item"),
                description=str(rec.get("description") or ""),
                item_type=str(rec.get("category") or "Arma"),
                subcategory=str(rec.get("subcategory") or ""),
                rarity=str(rec.get("rarity") or "common"),
                level_req=int(rec.get("level") or 1),
                stats=json.dumps(coerce_import_stats(stats_in, _ITEM_JSON_FIELDS, _ITEM_BOOL_FIELDS),
                                 ensure_ascii=False),
            )
            last_id = item_id
        self._reload_items(select_id=last_id)
        return last_id

    def _import_skill_records(self, records: list[dict]) -> str | None:
        """The actual skill-create loop, used by the Importar cards
        (ItemsImportExportMixin). Every key beyond _SKILL_DB_COLUMNS falls
        into the `stats` JSON blob — see import_export_constants.py for why
        that needs coerce_import_stats rather than a plain dict comprehension."""
        if not self._uow:
            return None
        existing = [s.get("code", "") for s in self._skills]
        last_id = None
        for rec in records:
            if not isinstance(rec, dict) or not rec.get("name"):
                continue
            skill_id = str(uuid.uuid4())
            code = self._next_code("SKL_", existing, start=1, width=3)
            existing.append(code)
            stats_in = {k: v for k, v in rec.items() if k not in _SKILL_DB_COLUMNS}
            self._uow.skills.create(
                id=skill_id, code=code,
                name=str(rec.get("name") or "Nova Habilidade"),
                description=str(rec.get("description") or ""),
                category=str(rec.get("category") or "Ataque"),
                rarity=str(rec.get("rarity") or "common"),
                level=int(rec.get("level") or 1),
                cooldown=float(rec.get("cooldown") or 0),
                mana_cost=int(rec.get("mana_cost") or 0),
                element=str(rec.get("element") or ""),
                stats=json.dumps(coerce_import_stats(stats_in, _SKILL_JSON_FIELDS, _SKILL_BOOL_FIELDS),
                                 ensure_ascii=False),
            )
            last_id = skill_id
        self._reload_skills(select_id=last_id)
        return last_id

    def _tree_export_rows(self) -> list[dict]:
        """One row per node across every guia da Árvore de Habilidades —
        trees are a graph (nodes+edges+per-guia theme), not a flat catalog
        record like items/skills, so they don't fit _export_rows()'s
        DB-column + stats-blob shape; this builds the flattened row shape
        Importar/Exportar uses instead (see _TREE_TEMPLATE_FIELDS in
        import_export_constants.py). Skill references are by NAME (not the
        internal uuid) so the export is portable/human-editable, same
        reasoning as "Item Requerido" in skill_editor.py."""
        if not self._uow:
            return []
        skills_by_id = {s["id"]: s for s in self._skills}
        rows: list[dict] = []
        for tree in self._uow.skill_trees.get_all_ordered():
            data = SkillTreeCanvas._parse_data(tree.get("data"))
            nodes = data.get("nodes", [])
            edges_by_src: dict[str, list[str]] = {}
            for pair in data.get("edges", []):
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    edges_by_src.setdefault(pair[0], []).append(pair[1])
            names_by_id = {n.get("id"): (skills_by_id.get(n.get("id")) or {}).get("name") or n.get("name", "")
                           for n in nodes}
            for node in nodes:
                node_id = node.get("id")
                connects = [names_by_id.get(dst, dst) for dst in edges_by_src.get(node_id, [])]
                rows.append({
                    "tree": tree.get("name", ""),
                    "theme_color": data.get("theme_color", "") or "",
                    "text_color": data.get("text_color", "") or "",
                    "skill": names_by_id.get(node_id, ""),
                    "rank_current": node.get("rank_current", 0),
                    "rank_max": node.get("rank_max", 1),
                    "pos_x": node.get("x", 0),
                    "pos_y": node.get("y", 0),
                    "connects_to": ";".join(c for c in connects if c),
                })
        return rows

    def _import_tree_records(self, records: list[dict]) -> str | None:
        """The actual guia-create/merge loop, used by the Importar cards.
        Each row is one NODE (see _TREE_TEMPLATE_FIELDS) — rows sharing the
        same "tree" name are grouped back into one guia, found-or-created by
        the same `name.lower().replace(" ", "_")` tree_key slug
        SkillTreeCanvas.create_tab_for_skill uses, so re-importing the same
        export updates that guia instead of duplicating it. "skill" must
        match an already-cadastrada Habilidade by name (a node can't exist
        for a skill that doesn't exist); unmatched rows are skipped.
        "connects_to" edges are only added between nodes THIS import
        actually created/updated — a stray reference can't create a
        dangling edge to a node that isn't in the row set."""
        if not self._uow:
            return None
        skills_by_name = {}
        for s in self._skills:
            skills_by_name.setdefault((s.get("name") or "").strip().lower(), s)

        trees_in_order: list[str] = []
        grouped: dict[str, list[dict]] = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            tree_name = str(rec.get("tree") or "").strip()
            skill_name = str(rec.get("skill") or "").strip()
            if not tree_name or not skill_name:
                continue
            grouped.setdefault(tree_name, [])
            if tree_name not in trees_in_order:
                trees_in_order.append(tree_name)
            grouped[tree_name].append(rec)

        existing_trees = {t["tree_key"]: t for t in self._uow.skill_trees.get_all_ordered()}
        last_key = None
        for tree_name in trees_in_order:
            rows = grouped[tree_name]
            key = tree_name.lower().replace(" ", "_")
            existing = existing_trees.get(key)
            prior_data = SkillTreeCanvas._parse_data(existing.get("data")) if existing else {"nodes": [], "edges": []}

            theme_color = next((r.get("theme_color") for r in rows if r.get("theme_color")), prior_data.get("theme_color", ""))
            text_color = next((r.get("text_color") for r in rows if r.get("text_color")), prior_data.get("text_color", ""))

            nodes_by_skill_id: dict[str, dict] = {n.get("id"): n for n in prior_data.get("nodes", [])}
            row_skill_ids: dict[str, str] = {}  # normalized skill name -> id, only for names seen THIS import
            for row in rows:
                skill = skills_by_name.get(str(row.get("skill") or "").strip().lower())
                if not skill:
                    continue
                skill_id = skill["id"]
                row_skill_ids[str(row.get("skill")).strip().lower()] = skill_id
                rank_max_cap = SkillTreeCanvas._skill_rank_max(skill)
                try:
                    rank_max_row = int(float(row.get("rank_max"))) if row.get("rank_max") not in (None, "") else rank_max_cap
                except (TypeError, ValueError):
                    rank_max_row = rank_max_cap
                rank_max_row = max(1, min(10, rank_max_row))
                try:
                    rank_current = max(0, min(rank_max_row, int(float(row.get("rank_current") or 0))))
                except (TypeError, ValueError):
                    rank_current = 0
                try:
                    x = float(row.get("pos_x") or 0)
                except (TypeError, ValueError):
                    x = 0.0
                try:
                    y = float(row.get("pos_y") or 0)
                except (TypeError, ValueError):
                    y = 0.0
                nodes_by_skill_id[skill_id] = {
                    "id": skill_id, "name": skill.get("name", ""), "icon": skill.get("icon") or "✨",
                    "image_path": skill.get("image_path") or "",
                    "color": item_rarity_color(skill.get("rarity", "common")),
                    "x": x, "y": y,
                    "rank_current": rank_current, "rank_max": rank_max_row,
                }

            edges: list[list[str]] = [
                list(pair) for pair in prior_data.get("edges", [])
                if isinstance(pair, (list, tuple)) and len(pair) == 2
            ]
            existing_edge_pairs = {tuple(e) for e in edges}
            for row in rows:
                src_id = row_skill_ids.get(str(row.get("skill") or "").strip().lower())
                if not src_id:
                    continue
                targets = [t.strip() for t in str(row.get("connects_to") or "").split(";") if t.strip()]
                for target_name in targets:
                    dst_skill = skills_by_name.get(target_name.lower())
                    dst_id = dst_skill["id"] if dst_skill else None
                    if not dst_id or dst_id not in nodes_by_skill_id:
                        continue  # no dangling edges to a node that isn't (and won't be) part of this tree
                    pair = (src_id, dst_id)
                    if pair not in existing_edge_pairs:
                        edges.append(list(pair))
                        existing_edge_pairs.add(pair)

            tree_data = {
                "nodes": list(nodes_by_skill_id.values()), "edges": edges,
                "theme_color": theme_color or "", "text_color": text_color or "",
            }
            self._uow.skill_trees.upsert(
                key, name=tree_name, icon=(existing.get("icon") if existing else "") or "✨",
                sort_order=(existing.get("sort_order") if existing else len(existing_trees)),
                data=json.dumps(tree_data, ensure_ascii=False),
            )
            existing_trees[key] = {"tree_key": key}
            last_key = key

        self._skill_tree.reload()
        return last_key

    @staticmethod
    def _parse_json_list(text: str) -> list[dict]:
        """Permissive parse (tolerates a bare object, // comments, trailing
        commas) → list of dicts. Raises ValueError with a friendly message.
        Shared with Dungeons e Construções — see
        dungeons.constants.parse_json_records."""
        from src.layouts.panels.dungeons.constants import parse_json_records
        return parse_json_records(text)

    # ── helpers ──

    @staticmethod
    def _next_code(prefix: str, existing: list[str], start: int = 1, width: int = 0) -> str:
        """Next free "PREFIXnnnn" not already used — scans existing codes for
        the max numeric suffix and adds one."""
        max_n = start - 1
        for code in existing:
            if code and code.startswith(prefix):
                tail = code[len(prefix):]
                if tail.isdigit():
                    max_n = max(max_n, int(tail))
        n = max_n + 1
        return f"{prefix}{n:0{width}d}" if width else f"{prefix}{n}"

    # ── paint (glass card, same as MobsPanel) ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        p.fillPath(path, QColor(14, 22, 42, 230))
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.0))
        p.drawPath(path)
        p.end()
