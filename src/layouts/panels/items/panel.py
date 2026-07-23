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
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors
from src.services.project_assets import import_asset, resolve_asset_path
from src.layouts.panels.mobs.categories import item_rarity_label
from src.layouts.panels.items.constants import (
    ITEM_CATEGORY_NAMES, SKILL_CATEGORIES,
    category_display, rarity_options,
)
from src.layouts.panels.items.entity_list import EntityListColumn
from src.layouts.panels.items.item_editor import ItemEditor
from src.layouts.panels.items.item_preview import ItemPreview
from src.layouts.panels.items.skill_editor import SkillEditor
from src.layouts.panels.items.skill_tree import SkillTreeCanvas

logger = logging.getLogger("MAKEMAP")

# Emoji shown in the list column per category, so a row reads at a glance
# without needing each record to carry an image.
_ITEM_CAT_ICONS = {
    "Arma": "🗡", "Armadura": "🛡", "Consumível": "🧪", "Material": "⛏",
    "Receita": "📜", "Missão": "🗝", "Outro": "📦",
}


class ItemsSkillsPanel(QWidget):
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
        self._current_item_id = ""
        self._current_skill_id = ""
        self._user_dragged: set[int] = set()  # ids() of splitters the user adjusted
        self._auto_positions: dict[int, dict[int, int]] = {}
        self._syncing = False  # guards the column-splitter mirror against recursion

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
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.TEXT_MUTED}; border: none; font-size: 14px; border-radius: 14px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.closed.emit)
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
        self._item_list.json_apply.connect(self._on_items_json)
        self._item_list.delete_requested.connect(self._on_item_delete)
        self._item_list.set_json_template(
            '[\n'
            '  { "name": "Espada Longa", "category": "Arma", "subcategory": "Espada",\n'
            '    "rarity": "rare", "level": 10 },\n'
            '  { "name": "Poção de Vida", "category": "Consumível", "rarity": "common" }\n'
            ']'
        )
        self._item_editor = ItemEditor()
        self._item_editor.changed.connect(self._item_save_timer.start)
        self._item_preview = ItemPreview()
        self._item_preview.import_button.clicked.connect(self._item_editor._on_pick_image)
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
        self._skill_list = EntityListColumn(
            "Habilidades", "+ Nova Habilidade",
            filters=[("Todas as Categorias", SKILL_CATEGORIES), ("Todas as Raridades", rarity_labels)],
        )
        self._skill_list.new_requested.connect(self._on_new_skill)
        self._skill_list.selected.connect(self._on_skill_selected)
        self._skill_list.json_apply.connect(self._on_skills_json)
        self._skill_list.delete_requested.connect(self._on_skill_delete)
        self._skill_list.set_json_template(
            '[\n'
            '  { "name": "Bola de Fogo", "category": "Ataque", "rarity": "rare",\n'
            '    "level": 5, "cooldown": 8, "mana_cost": 30, "element": "Fogo" },\n'
            '  { "name": "Escudo Sagrado", "category": "Defesa", "rarity": "epic" }\n'
            ']'
        )
        self._skill_editor = SkillEditor(skills_provider=lambda: self._skills)
        self._skill_editor.changed.connect(self._skill_save_timer.start)
        self._skill_tree = SkillTreeCanvas(self._uow, skills_provider=lambda: self._skills)

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
        outer.addWidget(self._rows_splitter, 1)

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

    def _on_item_selected(self, item_id: str):
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
            })
        self._skill_list.set_rows(rows)
        if hasattr(self, "_skill_editor"):
            self._skill_editor.refresh_evolves_from_options()
        if select_id:
            self._skill_list.select(select_id)
            self._on_skill_selected(select_id)
        elif not self._current_skill_id:
            self._skill_editor.set_empty()

    def _skill_by_id(self, skill_id: str) -> dict | None:
        return next((s for s in self._skills if s["id"] == skill_id), None)

    def _on_skill_selected(self, skill_id: str):
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
        new_tab_name = values.pop("_new_tab_name", "")
        if values.get("image_path"):
            values["image_path"] = import_asset(
                self._project_dir, values["image_path"], "assets/skills", self._current_skill_id)
        self._uow.skills.update(self._current_skill_id, **values)
        record = self._skill_by_id(self._current_skill_id)
        if record:
            record.update(values)
        self._reload_skills()
        self._skill_list.select(self._current_skill_id)
        # "Evoluir de: Nenhuma (raiz)" + um nome digitado cria (ou reaproveita)
        # a guia antes de garantir o nó — sem isso não haveria guia nenhuma
        # pra colocar o nó de uma primeira habilidade raiz.
        if not values.get("evolves_from") and new_tab_name and record:
            self._skill_tree.create_tab_for_skill(record, new_tab_name)
        # A árvore só ganha nó/conexão quando a habilidade é salva — reflete
        # o que "Evoluir de:" descreve, não o contrário.
        self._skill_tree.sync_skill_node(self._current_skill_id, values.get("evolves_from"))

    def _on_skill_delete(self, skill_id: str):
        if not self._uow:
            return
        record = self._skill_by_id(skill_id)
        name = record.get("name") if record else skill_id
        reply = QMessageBox.question(
            self, "Excluir habilidade", f'Excluir "{name}"? Essa ação não pode ser desfeita.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._uow.skills.delete(skill_id)
        self._skill_tree.remove_skill_node(skill_id)
        if self._current_skill_id == skill_id:
            self._current_skill_id = ""
        self._reload_skills()
        logger.info("Habilidade excluída: id=%s", skill_id)

    # ── JSON bulk create ──

    def _on_items_json(self, text: str):
        try:
            records = self._parse_json_list(text)
        except ValueError as exc:
            self._item_list.json_show_error(str(exc))
            return
        existing = [i.get("code", "") for i in self._items]
        last_id = None
        for rec in records:
            item_id = str(uuid.uuid4())
            code = self._next_code("ITM_", existing, start=1001)
            existing.append(code)
            self._uow.items.create(
                id=item_id, code=code,
                name=str(rec.get("name") or "Novo Item"),
                item_type=str(rec.get("category") or "Arma"),
                subcategory=str(rec.get("subcategory") or ""),
                rarity=str(rec.get("rarity") or "common"),
                level_req=int(rec.get("level") or 1),
                stats=json.dumps({k: v for k, v in rec.items()
                                  if k not in ("name", "category", "subcategory", "rarity", "level")},
                                 ensure_ascii=False),
            )
            last_id = item_id
        self._item_list.json_close()
        self._reload_items(select_id=last_id)
        logger.info("Itens criados via JSON: %d", len(records))

    def _on_skills_json(self, text: str):
        try:
            records = self._parse_json_list(text)
        except ValueError as exc:
            self._skill_list.json_show_error(str(exc))
            return
        existing = [s.get("code", "") for s in self._skills]
        last_id = None
        for rec in records:
            skill_id = str(uuid.uuid4())
            code = self._next_code("SKL_", existing, start=1, width=3)
            existing.append(code)
            self._uow.skills.create(
                id=skill_id, code=code,
                name=str(rec.get("name") or "Nova Habilidade"),
                category=str(rec.get("category") or "Ataque"),
                rarity=str(rec.get("rarity") or "common"),
                level=int(rec.get("level") or 1),
                cooldown=float(rec.get("cooldown") or 0),
                mana_cost=int(rec.get("mana_cost") or 0),
                element=str(rec.get("element") or ""),
                stats=json.dumps({k: v for k, v in rec.items()
                                  if k not in ("name", "category", "rarity", "level",
                                               "cooldown", "mana_cost", "element")},
                                 ensure_ascii=False),
            )
            last_id = skill_id
        self._skill_list.json_close()
        self._reload_skills(select_id=last_id)
        logger.info("Habilidades criadas via JSON: %d", len(records))

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
