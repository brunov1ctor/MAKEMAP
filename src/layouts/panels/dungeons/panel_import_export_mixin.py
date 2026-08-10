"""DungeonsImportExportMixin — the Importar (JSON/CSV paste + Excel drop +
"Imagens (pasta)") / Exportar (read-only JSON/CSV view + direct-to-file
Excel) tools panel that takes over the whole body of DungeonsPanel while
active. One set of cards is shared by a Dungeons/Construções toggle instead
of duplicating everything twice — see _set_entity_mode.

The card-building/export/import mechanics themselves (which dispatch
through the `_current_*` protocol below) live in
src/layouts/panels/shared/import_export_mixin.py's EntityModeImportExportMixin
— byte-identical to items/panel_import_export_mixin.py's
ItemsImportExportMixin before this module was split, so it's shared rather
than duplicated. What's left here is genuinely Dungeons/Construções-
specific: the `_current_*` dispatch itself, the JSON/CSV template text, the
image-match preview/apply (Dungeons/Construções' `image` column and
reload_dungeons/reload_buildings dispatch), and the export/save/xlsx
methods (their default filenames differ per entity).

Mixed into DungeonsPanel (see panel.py) — operates on self.* attributes
that panel owns (self._dungeons, self._buildings, self._uow,
self._project_dir, self._body_stack, self._dungeon_tabs,
self._building_tabs, ...); not meant to be instantiated on its own.
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
from src.layouts.panels.dungeons.import_export_constants import (
    _DUNGEON_TEMPLATE_FIELDS, _DUNGEON_TEMPLATE_DOCS, _DUNGEON_DB_COLUMNS, _DUNGEON_JSON_FIELDS,
    _BUILDING_TEMPLATE_FIELDS, _BUILDING_TEMPLATE_DOCS, _BUILDING_DB_COLUMNS, _BUILDING_JSON_FIELDS,
)
from src.layouts.panels.shared.import_export_helpers import build_tools_header, build_export_view_page
from src.layouts.panels.shared.import_export_mixin import EntityModeImportExportMixin
from src.services.project_assets import import_asset

logger = logging.getLogger("MAKEMAP")


class DungeonsImportExportMixin(EntityModeImportExportMixin):
    """The body's alternate page (see self._body_stack) — a header (title
    + Dungeons/Construções toggle + ✕ close) above a stack of its own:
    page 0 is Importar (JSON/CSV paste, Excel drop, Imagens por pasta),
    page 1 is a read-only export view."""

    # ─── entity-mode plumbing ───

    def _current_entity_label(self) -> str:
        return {"dungeon": "Dungeons", "building": "Construções"}[self._import_entity_mode]

    def _current_catalog(self) -> list[dict]:
        return self._dungeons if self._import_entity_mode == "dungeon" else self._buildings

    def _current_repo(self):
        return self._uow.dungeons if self._import_entity_mode == "dungeon" else self._uow.buildings

    def _current_fields(self) -> dict:
        return _DUNGEON_TEMPLATE_FIELDS if self._import_entity_mode == "dungeon" else _BUILDING_TEMPLATE_FIELDS

    def _current_db_columns(self) -> dict:
        """template key -> real repository column — identity map here (see
        import_export_constants.py docstring: unlike items/skills, Dungeons/
        Construções already have a real DB column for every field, no
        overflow `stats` blob)."""
        return _DUNGEON_DB_COLUMNS if self._import_entity_mode == "dungeon" else _BUILDING_DB_COLUMNS

    def _current_json_fields(self) -> tuple:
        return _DUNGEON_JSON_FIELDS if self._import_entity_mode == "dungeon" else _BUILDING_JSON_FIELDS

    def _current_docs(self) -> list[tuple[str, str]]:
        return _DUNGEON_TEMPLATE_DOCS if self._import_entity_mode == "dungeon" else _BUILDING_TEMPLATE_DOCS

    def _current_categories(self) -> list[str]:
        """Only feeds the JSON template's "Categorias/Tipos disponíveis"
        hint line — pulled live from the editable tab lists (dungeon_types/
        building_categories) rather than a fixed list."""
        if not self._uow:
            return []
        if self._import_entity_mode == "dungeon":
            return [t["name"] for t in self._uow.dungeon_types.get_all()]
        return [c["name"] for c in self._uow.building_categories.get_all()]

    def _current_required_keys(self) -> tuple[str, ...]:
        return ("name",)

    def _current_asset_folder(self) -> str:
        return "assets/dungeons" if self._import_entity_mode == "dungeon" else "assets/buildings"

    def _current_import_fn(self):
        return self._import_dungeon_records if self._import_entity_mode == "dungeon" else self._import_building_records

    def _image_folder_hint_text(self) -> str:
        return (
            "Escolha uma pasta com imagens nomeadas como as dungeons/construções "
            "(ex.: \"Cripta Gelada.png\") — cada arquivo cujo nome bater com um "
            "registro existente recebe essa imagem."
        )

    def _set_entity_mode(self, mode: str):
        if mode == self._import_entity_mode:
            return
        self._import_entity_mode = mode
        for btn, btn_mode in self._entity_mode_buttons:
            active = btn_mode == mode
            btn.setStyleSheet(self._entity_toggle_style(active))
        # Data typed/staged for one entity type isn't valid input for the
        # other — clear every card's in-progress state on switch rather
        # than risk silently applying Dungeons JSON as Construções or vice
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
        for mode, label in (("dungeon", "Dungeons"), ("building", "Construções")):
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
        user's real data (Aplicar always CREATES new rows, so prefilling
        real data risks silently duplicating it)."""
        example = dict(self._current_fields())
        example["name"] = "Nova Dungeon" if self._import_entity_mode == "dungeon" else "Nova Construção"
        return example

    def _json_import_template(self) -> str:
        """The immutable base template the JSON card's "Template" button
        always resets back to."""
        import json
        doc_lines = "\n".join(f"// {key}: {doc}" for key, doc in self._current_docs())
        hint_lines = [doc_lines]
        categories = self._current_categories()
        if categories:
            label = "Tipos" if self._import_entity_mode == "dungeon" else "Categorias"
            hint_lines.append(f"// {label} disponíveis: {', '.join(categories)}")
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
            suffix = " (substituirá imagem atual)" if rec.get("image") else ""
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
                repo.update(rec_id, image=rel_path)
                applied += 1
            except Exception:
                logger.exception("Falha ao atribuir imagem a %s (%s)", rec.get("name", ""), source_path)
        logger.info("Imagens atribuídas via pasta: %d %s", applied, self._current_entity_label())
        if self._import_entity_mode == "dungeon":
            self._reload_dungeons()
        else:
            self._reload_buildings()
        self._close_tools_mode()

    # ─── export ───

    def _export_rows(self, json_native: bool) -> list[dict]:
        """Builds one export row per catalog record. Unlike items/skills'
        _export_rows, there's no `stats` blob to parse — every field is
        already a real DB column (see import_export_constants.py) — so this
        just reads each field straight off the record, JSON-decoding the
        rewards/costs-style columns for a native JSON export or leaving
        them as the already-JSON-encoded text they're stored as for CSV/
        Excel (which can't hold a list/dict in a cell anyway)."""
        import json
        fieldnames = list(self._current_fields().keys())
        defaults = self._current_fields()
        json_fields = self._current_json_fields()
        rows = []
        for rec in self._current_catalog():
            row = {}
            for key in fieldnames:
                value = rec.get(key, defaults[key])
                if key in json_fields:
                    if json_native:
                        try:
                            value = json.loads(value) if isinstance(value, str) else (value if value is not None else defaults[key])
                        except (json.JSONDecodeError, TypeError):
                            value = defaults[key]
                    elif not isinstance(value, str):
                        value = json.dumps(value, ensure_ascii=False)
                row[key] = value
            rows.append(row)
        return rows

    def _on_save_export_file(self):
        fmt = self._template_fmt
        ext = "json" if fmt == "json" else "csv"
        file_filter = "JSON (*.json)" if fmt == "json" else "CSV (*.csv)"
        default_name = "dungeons" if self._import_entity_mode == "dungeon" else "construcoes"
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
        default_name = "dungeons" if self._import_entity_mode == "dungeon" else "construcoes"
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
        example = self._example_row()
        wb = Workbook()
        ws = wb.active
        ws.title = self._current_entity_label()
        ws.append(fieldnames)
        ws.append([json.dumps(example[k], ensure_ascii=False) if k in json_fields else example.get(k, "")
                   for k in fieldnames])
        wb.save(path)
        logger.info("Template Excel de %s baixado: %s", self._current_entity_label(), path)
