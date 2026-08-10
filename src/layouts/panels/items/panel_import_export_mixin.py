"""ItemsImportExportMixin — the Importar (JSON/CSV paste + Excel drop +
"Imagens (pasta)") / Exportar (read-only JSON/CSV view + direct-to-file
Excel) tools panel that takes over the whole body of ItemsSkillsPanel while
active. One set of cards is shared by an Itens/Habilidades/Árvores toggle
instead of duplicating everything twice — see _set_entity_mode.

The card-building/export/import mechanics themselves (which dispatch
through the `_current_*` protocol below) live in
src/layouts/panels/shared/import_export_mixin.py's EntityModeImportExportMixin
— byte-identical to dungeons/panel_import_export_mixin.py's
DungeonsImportExportMixin before this module was split, so it's shared
rather than duplicated. What's left here is genuinely Itens/Habilidades/
Árvores-specific: the `_current_*` dispatch itself (including the extra
"tree" mode fork — a skill tree is a graph, not a flat catalog, so several
of these methods have a 3rd branch dungeons/quests don't need), the JSON/
CSV template text, the image-match preview/apply (Items/Skills' image_path
column, no tree equivalent), and the export/save/xlsx methods.

Mixed into ItemsSkillsPanel (see panel.py) — operates on self.* attributes
that panel owns (self._items, self._skills, self._uow, self._project_dir,
self._body_stack, ...); not meant to be instantiated on its own.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QWidget, QStackedWidget, QScrollArea, QFileDialog,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.items.constants import ITEM_CATEGORY_NAMES, SKILL_CATEGORIES, rarity_options
from src.layouts.panels.items.import_export_constants import (
    _ITEM_TEMPLATE_FIELDS, _ITEM_TEMPLATE_DOCS, _ITEM_DB_COLUMNS, _ITEM_JSON_FIELDS,
    _SKILL_TEMPLATE_FIELDS, _SKILL_TEMPLATE_DOCS, _SKILL_DB_COLUMNS, _SKILL_JSON_FIELDS,
    _TREE_TEMPLATE_FIELDS, _TREE_TEMPLATE_DOCS,
)
from src.layouts.panels.shared.import_export_helpers import build_tools_header, build_export_view_page
from src.layouts.panels.shared.import_export_mixin import EntityModeImportExportMixin
from src.services.project_assets import import_asset

logger = logging.getLogger("MAKEMAP")


class ItemsImportExportMixin(EntityModeImportExportMixin):
    """The body's alternate page (see self._body_stack) — a header (title
    + Itens/Habilidades/Árvores toggle + ✕ close) above a stack of its own:
    page 0 is Importar (JSON/CSV paste, Excel drop, Imagens por pasta), page
    1 is a read-only export view."""

    # ─── entity-mode plumbing ───

    def _current_entity_label(self) -> str:
        return {"item": "Itens", "skill": "Habilidades", "tree": "Árvores"}[self._import_entity_mode]

    def _current_catalog(self) -> list[dict]:
        if self._import_entity_mode == "item":
            return self._items
        if self._import_entity_mode == "skill":
            return self._skills
        # Trees are a graph, not a flat catalog — one row per NODE across
        # every guia (see panel.py._tree_export_rows), not one row per
        # skill_trees table row.
        return self._tree_export_rows()

    def _current_repo(self):
        """Only used by the "Imagens (pasta)" card (item_type-independent
        image-by-name matching) — hidden entirely in tree mode (see
        _set_entity_mode), so this never actually needs a tree branch."""
        return self._uow.items if self._import_entity_mode == "item" else self._uow.skills

    def _current_fields(self) -> dict:
        return {"item": _ITEM_TEMPLATE_FIELDS, "skill": _SKILL_TEMPLATE_FIELDS,
                "tree": _TREE_TEMPLATE_FIELDS}[self._import_entity_mode]

    def _current_db_columns(self) -> dict:
        """template key -> real repository column, for the fields that
        AREN'T in `stats` (see import_export_constants.py). Empty for
        trees — they don't have a stats-blob/DB-column split at all, see
        _tree_export_rows/_import_tree_records in panel.py."""
        return {"item": _ITEM_DB_COLUMNS, "skill": _SKILL_DB_COLUMNS, "tree": {}}[self._import_entity_mode]

    def _current_json_fields(self) -> tuple:
        """Which stats keys hold a list/dict (tags, rank_damage) rather
        than a scalar — these get JSON-encoded into a single CSV/Excel
        cell (see _export_rows) since those formats can't hold a list
        natively the way a JSON export can. Empty for trees — their one
        list-shaped field (connects_to) is already plain ";"-joined text,
        see _TREE_TEMPLATE_FIELDS."""
        return {"item": _ITEM_JSON_FIELDS, "skill": _SKILL_JSON_FIELDS, "tree": ()}[self._import_entity_mode]

    def _current_docs(self) -> list[tuple[str, str]]:
        return {"item": _ITEM_TEMPLATE_DOCS, "skill": _SKILL_TEMPLATE_DOCS,
                "tree": _TREE_TEMPLATE_DOCS}[self._import_entity_mode]

    def _current_categories(self) -> list[str]:
        """Only feeds the JSON template's "Categorias disponíveis" hint
        line — trees have no category concept, so an empty list here
        suppresses that line (see _json_import_template)."""
        return {"item": ITEM_CATEGORY_NAMES, "skill": SKILL_CATEGORIES, "tree": []}[self._import_entity_mode]

    def _current_required_keys(self) -> tuple[str, ...]:
        """Which keys a CSV/Excel row must have a value for to count as a
        real record — items/skills need a name, a tree-node row needs both
        the guia name and the skill it references (see
        _TREE_TEMPLATE_FIELDS/_import_tree_records)."""
        return ("tree", "skill") if self._import_entity_mode == "tree" else ("name",)

    def _current_asset_folder(self) -> str:
        return "assets/items" if self._import_entity_mode == "item" else "assets/skills"

    def _current_import_fn(self):
        return {"item": self._import_item_records, "skill": self._import_skill_records,
                "tree": self._import_tree_records}[self._import_entity_mode]

    def _image_folder_hint_text(self) -> str:
        return (
            "Escolha uma pasta com imagens nomeadas como os itens/habilidades "
            "(ex.: \"Espada Longa.png\") — cada arquivo cujo nome bater com um "
            "registro existente recebe essa imagem."
        )

    def _set_entity_mode(self, mode: str):
        if mode == self._import_entity_mode:
            return
        self._import_entity_mode = mode
        for btn, btn_mode in self._entity_mode_buttons:
            active = btn_mode == mode
            btn.setStyleSheet(self._entity_toggle_style(active))
        # "Imagens (pasta)" has no tree equivalent (a guia isn't a single
        # image-able record) — hide it instead of leaving a dead control.
        if hasattr(self, "_image_folder_card"):
            self._image_folder_card.setVisible(mode != "tree")
        # Data typed/staged for one entity type isn't valid input for the
        # other — clear every card's in-progress state on switch rather
        # than risk silently applying Itens JSON as Habilidades or vice
        # versa.
        for reset in self._entity_mode_reset_callbacks:
            reset()

    # ─── tools panel shell ───

    def _build_tools_panel(self) -> QWidget:
        self._entity_mode_buttons: list[tuple[QToolButton, str]] = []
        self._entity_mode_reset_callbacks: list = []

        panel = QFrame()
        panel.setStyleSheet("QFrame { background: rgba(255,255,255,0.03); border-radius: 8px; }")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        head_row, self._tools_title_lbl, _tools_close_btn = build_tools_header(self._close_tools_mode)
        outer.addLayout(head_row)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_lbl = QLabel("Aplicar em:")
        mode_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        mode_row.addWidget(mode_lbl)
        for mode, label in (("item", "Itens"), ("skill", "Habilidades"), ("tree", "Árvores")):
            btn = QToolButton()
            btn.setText(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mode: self._set_entity_mode(m))
            mode_row.addWidget(btn)
            self._entity_mode_buttons.append((btn, mode))
        mode_row.addStretch()
        outer.addLayout(mode_row)
        for btn, mode in self._entity_mode_buttons:
            btn.setStyleSheet(self._entity_toggle_style(mode == self._import_entity_mode))

        self._tools_stack = QStackedWidget()

        # ── Page 0: Importar ──
        import_content = QWidget()
        import_lay = QVBoxLayout(import_content)
        import_lay.setContentsMargins(0, 0, 0, 0)
        import_lay.setSpacing(8)
        import_lay.addWidget(self._build_text_import_card(
            "JSON", "Cole uma lista JSON para criar vários de uma vez.", "json"))
        import_lay.addWidget(self._build_text_import_card(
            "CSV", "Cole uma lista CSV para criar vários de uma vez.", "csv"))
        import_lay.addWidget(self._build_excel_import_card())
        self._image_folder_card = self._build_image_folder_import_card()
        import_lay.addWidget(self._image_folder_card)
        self._image_folder_card.setVisible(self._import_entity_mode != "tree")
        import_lay.addStretch()
        import_scroll = QScrollArea()
        import_scroll.setWidgetResizable(True)
        import_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        import_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                                     "QScrollArea > QWidget > QWidget { background: transparent; }")
        import_scroll.setWidget(import_content)
        self._tools_stack.addWidget(import_scroll)

        # ── Page 1: read-only JSON/CSV export view ──
        template_page, self._template_hint_lbl, self._template_edit = build_export_view_page(self._on_save_export_file)
        self._tools_stack.addWidget(template_page)
        outer.addWidget(self._tools_stack, 1)
        return panel

    # ─── Importar cards (JSON/CSV paste, Excel drop) ───

    def _example_row(self) -> dict:
        """The "Template" button's single documented example row — not the
        user's real data (Aplicar always CREATES new rows/nodes, so
        prefilling real data risks silently duplicating it). Item/skill
        rows are keyed by "name"; a tree row is one NODE, keyed by
        "tree"+"skill" instead (see _TREE_TEMPLATE_FIELDS)."""
        example = dict(self._current_fields())
        if self._import_entity_mode == "item":
            example["name"] = "Novo Item"
        elif self._import_entity_mode == "skill":
            example["name"] = "Nova Habilidade"
        else:
            example["tree"] = "Minha Árvore"
            example["skill"] = "Nome de uma habilidade já cadastrada"
        return example

    def _json_import_template(self) -> str:
        """The immutable base template the JSON card's "Template" button
        always resets back to."""
        import json
        doc_lines = "\n".join(f"// {key}: {doc}" for key, doc in self._current_docs())
        hint_lines = [doc_lines]
        # Categoria/raridade hints only apply to item/skill — a tree row
        # has neither concept (see _current_categories/_TREE_TEMPLATE_FIELDS).
        categories = self._current_categories()
        if categories:
            hint_lines.append(f"// Categorias disponíveis: {', '.join(categories)}")
        if "rarity" in self._current_fields():
            hint_lines.append(f"// Raridades disponíveis: {', '.join(key for key, _label in rarity_options())}")
        row_json = json.dumps(self._example_row(), ensure_ascii=False, indent=2)
        row_indented = "\n".join(f"  {line}" for line in row_json.splitlines())
        return "\n".join(hint_lines) + f"\n[\n{row_indented}\n]"

    def _csv_import_template(self) -> str:
        import csv
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(self._current_fields().keys()))
        writer.writeheader()
        writer.writerow(self._example_row())
        return buf.getvalue()

    # ─── Imagens (pasta) ───

    @staticmethod
    def _format_image_match_preview(matches: list, unmatched: list[str]) -> str:
        lines = [f"{len(matches) + len(unmatched)} imagem(ns) encontradas, {len(matches)} correspondente(s):"]
        for rec, path in matches:
            suffix = " (substituirá imagem atual)" if rec.get("image_path") else ""
            lines.append(f"  OK {rec.get('name', '')}  <-  {os.path.basename(path)}{suffix}")
        if unmatched:
            lines.append(f"{len(unmatched)} arquivo(s) sem correspondência:")
            for name in unmatched:
                lines.append(f"  - {name}")
        return "\n".join(lines)

    def _apply_image_matches(self, matches: list):
        if not self._uow:
            return
        repo = self._current_repo()
        folder = self._current_asset_folder()
        applied = 0
        for rec, source_path in matches:
            rec_id = rec.get("id")
            if not rec_id:
                continue
            try:
                rel_path = import_asset(self._project_dir, source_path, folder, rec_id)
                repo.update(rec_id, image_path=rel_path)
                applied += 1
            except Exception:
                logger.exception("Falha ao atribuir imagem a %s (%s)", rec.get("name", ""), source_path)
        logger.info("Imagens atribuídas via pasta: %d %s", applied, self._current_entity_label())
        if self._import_entity_mode == "item":
            self._reload_items()
        else:
            self._reload_skills()
        self._close_tools_mode()

    # ─── export ───

    def _export_rows(self, json_native: bool) -> list[dict]:
        """Builds one export row per catalog record, merging its real DB
        columns with its parsed `stats` blob so Exportar is lossless —
        it used to only pull the handful of DB columns and silently drop
        everything in `stats` (rank tables, tags, combat stats, flags...).

        `json_native=True` (JSON export) keeps list/dict values as real
        Python objects; `False` (CSV/Excel, which can't hold a list in a
        cell) JSON-encodes just the _current_json_fields() values into a
        string instead.

        Trees don't have a `stats` blob (or a DB-column split) at all —
        _current_catalog() already returns rows in the exact
        _TREE_TEMPLATE_FIELDS shape (see panel.py._tree_export_rows), so
        they're returned as-is rather than run through the parse-stats
        logic below, which would just overwrite every value with its
        default (no "stats" key to read on a flattened node row)."""
        if self._import_entity_mode == "tree":
            return list(self._current_catalog())
        import json
        fieldnames = list(self._current_fields().keys())
        defaults = self._current_fields()
        db_columns = self._current_db_columns()
        json_fields = self._current_json_fields()
        rows = []
        for rec in self._current_catalog():
            try:
                stats = json.loads(rec.get("stats") or "{}")
                if not isinstance(stats, dict):
                    stats = {}
            except (json.JSONDecodeError, TypeError):
                stats = {}
            row = {}
            for key in fieldnames:
                if key in db_columns:
                    value = rec.get(db_columns[key], defaults[key])
                else:
                    value = stats.get(key, defaults[key])
                if not json_native and key in json_fields:
                    value = json.dumps(value, ensure_ascii=False)
                row[key] = value
            rows.append(row)
        return rows

    def _on_save_export_file(self):
        fmt = self._template_fmt
        ext = "json" if fmt == "json" else "csv"
        file_filter = "JSON (*.json)" if fmt == "json" else "CSV (*.csv)"
        default_name = "itens" if self._import_entity_mode == "item" else "habilidades"
        path, _selected = QFileDialog.getSaveFileName(
            self, "Salvar Exportação", f"{default_name}.{ext}", file_filter)
        if not path:
            return
        if not path.lower().endswith(f".{ext}"):
            path += f".{ext}"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self._template_edit.toPlainText())
        logger.info("Exportação de %s salva: %s (%s, %d registro(s))", self._current_entity_label(), path, fmt, len(self._current_catalog()))

    def _export_xlsx(self):
        default_name = "itens" if self._import_entity_mode == "item" else "habilidades"
        path, _selected = QFileDialog.getSaveFileName(
            self, "Exportar (Excel)", f"{default_name}.xlsx", "Planilha Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        from openpyxl import Workbook

        fieldnames = list(self._current_fields().keys())
        rows = self._export_rows(json_native=False)  # Excel cells can't hold a list either
        wb = Workbook()
        ws = wb.active
        ws.title = self._current_entity_label()
        ws.append(fieldnames)
        for row in rows:
            ws.append([row[k] for k in fieldnames])
        wb.save(path)
        logger.info("%s exportado(s) para %s (%d linha(s))", self._current_entity_label(), path, len(rows))

    def _export_xlsx_blank_template(self):
        path, _selected = QFileDialog.getSaveFileName(
            self, "Baixar Template (Excel)", "template.xlsx", "Planilha Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        import json
        from openpyxl import Workbook

        fieldnames = list(self._current_fields().keys())
        json_fields = self._current_json_fields()
        example = dict(self._current_fields())
        example["name"] = "Novo Item" if self._import_entity_mode == "item" else "Nova Habilidade"
        wb = Workbook()
        ws = wb.active
        ws.title = self._current_entity_label()
        ws.append(fieldnames)
        # tags/rank_damage default to [] — an Excel cell can't hold a raw
        # Python list, same reasoning as _export_rows(json_native=False).
        ws.append([json.dumps(example[k], ensure_ascii=False) if k in json_fields else example.get(k, "")
                   for k in fieldnames])
        wb.save(path)
        logger.info("Template Excel de %s baixado: %s", self._current_entity_label(), path)
