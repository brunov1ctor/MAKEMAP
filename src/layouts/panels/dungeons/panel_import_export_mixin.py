"""DungeonsImportExportMixin — the Importar (JSON/CSV paste + Excel drop +
"Imagens (pasta)") / Exportar (read-only JSON/CSV view + direct-to-file
Excel) tools panel that takes over the whole body of DungeonsPanel while
active, mirroring items/panel_import_export_mixin.py's
ItemsImportExportMixin. One set of cards is shared by a Dungeons/
Construções toggle instead of duplicating everything twice — see
_set_entity_mode.

Mixed into DungeonsPanel (see panel.py) — operates on self.* attributes
that panel owns (self._dungeons, self._buildings, self._uow,
self._project_dir, self._body_stack, self._dungeon_tabs,
self._building_tabs, ...); not meant to be instantiated on its own.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QTextEdit,
    QPushButton, QWidget, QStackedWidget, QScrollArea, QFileDialog,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import parse_json_records
from src.layouts.panels.dungeons.import_export_constants import (
    _DUNGEON_TEMPLATE_FIELDS, _DUNGEON_TEMPLATE_DOCS, _DUNGEON_DB_COLUMNS, _DUNGEON_JSON_FIELDS,
    _BUILDING_TEMPLATE_FIELDS, _BUILDING_TEMPLATE_DOCS, _BUILDING_DB_COLUMNS, _BUILDING_JSON_FIELDS,
)
from src.layouts.panels.shared.import_export_helpers import (
    DropZone, normalize_name, index_files_by_stem, normalize_blank_cells,
    read_json, read_csv, read_xlsx, import_button_row,
)
from src.services.project_assets import import_asset

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

logger = logging.getLogger("MAKEMAP")


class DungeonsImportExportMixin:
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

    @staticmethod
    def _entity_toggle_style(active: bool) -> str:
        bg = Colors.ACCENT if active else "rgba(255,255,255,0.06)"
        fg = "#08131F" if active else Colors.TEXT_SECONDARY
        border = Colors.ACCENT if active else Colors.BORDER_SUBTLE
        return f"""
            QToolButton {{ background: {bg}; color: {fg}; border: 1px solid {border};
                border-radius: 6px; padding: 4px 14px; font-size: 10px; font-weight: bold; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """

    # ─── tools panel shell ───

    def _build_tools_panel(self) -> QWidget:
        self._entity_mode_buttons: list[tuple[QToolButton, str]] = []
        self._entity_mode_reset_callbacks: list = []

        panel = QFrame()
        panel.setStyleSheet("QFrame { background: rgba(255,255,255,0.03); border-radius: 8px; }")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        head_row = QHBoxLayout()
        self._tools_title_lbl = QLabel("")
        self._tools_title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        head_row.addWidget(self._tools_title_lbl, 1)
        tools_close_btn = QToolButton()
        tools_close_btn.setText("✕")
        tools_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tools_close_btn.setToolTip("Fechar")
        tools_close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 14px; padding: 2px 6px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        tools_close_btn.clicked.connect(self._close_tools_mode)
        head_row.addWidget(tools_close_btn)
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
        template_page = QWidget()
        template_lay = QVBoxLayout(template_page)
        template_lay.setContentsMargins(0, 0, 0, 0)
        template_lay.setSpacing(6)

        self._template_hint_lbl = QLabel("")
        self._template_hint_lbl.setWordWrap(True)
        self._template_hint_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        template_lay.addWidget(self._template_hint_lbl)

        self._template_edit = QTextEdit()
        self._template_edit.setReadOnly(True)
        self._template_edit.setStyleSheet(f"""
            QTextEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-family: Consolas, monospace;
                background: rgba(0,0,0,0.2); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 6px; }}
        """)
        template_lay.addWidget(self._template_edit, 1)

        template_btn_row = QHBoxLayout()
        template_btn_row.addStretch()
        template_save_btn = QPushButton("💾 Salvar Arquivo")
        template_save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        template_save_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        template_save_btn.clicked.connect(self._on_save_export_file)
        template_btn_row.addWidget(template_save_btn)
        template_lay.addLayout(template_btn_row)

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

    def _build_text_import_card(self, title: str, hint: str, fmt: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: rgba(0,0,0,0.15); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(title_lbl)
        hint_lbl = QLabel(hint)
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        lay.addWidget(hint_lbl)

        edit = QTextEdit()
        edit.setFixedHeight(120)
        edit.setStyleSheet(f"""
            QTextEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 9px; font-family: Consolas, monospace;
                background: rgba(0,0,0,0.25); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 5px; }}
        """)
        lay.addWidget(edit)

        error_lbl = QLabel("")
        error_lbl.setWordWrap(True)
        error_lbl.setStyleSheet(f"color: {Colors.ERROR}; font-size: 9px; background: transparent; border: none;")
        error_lbl.hide()
        lay.addWidget(error_lbl)

        def reset_to_template():
            edit.setPlainText(self._json_import_template() if fmt == "json" else self._csv_import_template())
            error_lbl.hide()

        def do_apply():
            text = edit.toPlainText()
            try:
                if fmt == "json":
                    data = parse_json_records(text, required_keys=self._current_required_keys())
                else:
                    import csv
                    import io
                    data = [normalize_blank_cells(dict(row)) for row in csv.DictReader(io.StringIO(text))]
                    required = self._current_required_keys()
                    data = [d for d in data if all(d.get(k) for k in required)]
                    if not data:
                        needed = " e ".join(f'"{k}"' for k in required)
                        raise ValueError(f"Nenhum registro válido (cada um precisa de {needed}).")
            except ValueError as exc:
                error_lbl.setText(str(exc))
                error_lbl.show()
                return
            except Exception:
                logger.exception("Falha ao interpretar import de %s (%s).", self._current_entity_label(), fmt)
                error_lbl.setText("Não foi possível interpretar o conteúdo — confira o formato.")
                error_lbl.show()
                return
            self._current_import_fn()(data)
            logger.info("Criado(s) %d %s via Importar (%s)", len(data), self._current_entity_label(), fmt)
            reset_to_template()
            self._close_tools_mode()

        row, _apply_btn = import_button_row(self._close_tools_mode, reset_to_template, do_apply)
        lay.addLayout(row)
        reset_to_template()
        self._entity_mode_reset_callbacks.append(reset_to_template)
        return card

    def _build_excel_import_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: rgba(0,0,0,0.15); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)

        title_lbl = QLabel("Excel")
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(title_lbl)

        drop_zone = DropZone()
        lay.addWidget(drop_zone)

        staged_lbl = QLabel("Nenhum arquivo selecionado.")
        staged_lbl.setWordWrap(True)
        staged_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        lay.addWidget(staged_lbl)

        state = {"path": ""}

        def on_file_staged(path: str):
            state["path"] = path
            staged_lbl.setText(f"Selecionado: {os.path.basename(path)}")
            apply_btn.setEnabled(True)

        drop_zone.file_chosen.connect(on_file_staged)

        def clear_staged():
            state["path"] = ""
            staged_lbl.setText("Nenhum arquivo selecionado.")
            apply_btn.setEnabled(False)

        def do_cancel():
            clear_staged()
            self._close_tools_mode()

        def do_apply():
            if not state["path"]:
                return
            self._on_file_dropped(state["path"])
            clear_staged()

        row, apply_btn = import_button_row(do_cancel, self._export_xlsx_blank_template, do_apply)
        apply_btn.setEnabled(False)
        lay.addLayout(row)
        self._entity_mode_reset_callbacks.append(clear_staged)
        return card

    def _on_file_dropped(self, path: str):
        if not self._uow:
            return
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        reader = {"json": read_json, "csv": read_csv, "xlsx": read_xlsx}.get(suffix)
        if reader is None:
            logger.warning("Formato de arquivo não suportado para import: %s", path)
            return
        try:
            data = reader(path)
        except Exception:
            logger.exception("Falha ao ler arquivo de importação: %s", path)
            return
        self._current_import_fn()(data)
        logger.info("Importado(s) %s de %s", self._current_entity_label(), path)
        self._close_tools_mode()

    # ─── Imagens (pasta) ───

    def _build_image_folder_import_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"QFrame {{ background: rgba(0,0,0,0.15); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)

        title_lbl = QLabel("Imagens (pasta)")
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(title_lbl)

        hint_lbl = QLabel(
            "Escolha uma pasta com imagens nomeadas como as dungeons/construções "
            "(ex.: \"Cripta Gelada.png\") — cada arquivo cujo nome bater com um "
            "registro existente recebe essa imagem."
        )
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        lay.addWidget(hint_lbl)

        pick_btn = QPushButton("📁 Selecionar Pasta")
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; padding: 5px 10px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); border-color: {Colors.ACCENT}; }}
        """)
        lay.addWidget(pick_btn)

        preview_edit = QTextEdit()
        preview_edit.setReadOnly(True)
        preview_edit.setFixedHeight(120)
        preview_edit.setStyleSheet(f"""
            QTextEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 9px; font-family: Consolas, monospace;
                background: rgba(0,0,0,0.2); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 6px; }}
        """)
        preview_edit.setPlainText("Nenhuma pasta selecionada.")
        lay.addWidget(preview_edit)

        state = {"matches": []}  # list of (record_dict, source_file_path)

        def refresh_preview():
            matches, unmatched = self._match_catalog_against_staged_folder()
            state["matches"] = matches
            preview_edit.setPlainText(self._format_image_match_preview(matches, unmatched))
            apply_btn.setEnabled(bool(matches))

        def on_pick_folder():
            folder = QFileDialog.getExistingDirectory(self, "Selecione a pasta com as imagens")
            if not folder:
                return
            self._staged_image_folder = folder
            self._staged_image_files = index_files_by_stem(folder, _IMAGE_EXTS)
            refresh_preview()

        pick_btn.clicked.connect(on_pick_folder)

        def clear_staged():
            state["matches"] = []
            preview_edit.setPlainText("Nenhuma pasta selecionada.")
            apply_btn.setEnabled(False)

        def do_cancel():
            state["matches"] = []
            self._close_tools_mode()

        def do_apply():
            if not state["matches"]:
                return
            self._apply_image_matches(state["matches"])
            clear_staged()

        row = QHBoxLayout()
        row.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY}; border: none;
                border-radius: 6px; padding: 5px 10px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        cancel_btn.clicked.connect(do_cancel)
        row.addWidget(cancel_btn)
        apply_btn = QPushButton("Aplicar")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 5px 12px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover:enabled {{ background: {Colors.ACCENT_HOVER}; }}
            QPushButton:disabled {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_MUTED}; }}
        """)
        apply_btn.setEnabled(False)
        apply_btn.clicked.connect(do_apply)
        row.addWidget(apply_btn)
        lay.addLayout(row)
        self._entity_mode_reset_callbacks.append(clear_staged)
        return card

    def _match_catalog_against_staged_folder(self) -> tuple[list, list[str]]:
        files_by_name = self._staged_image_files
        matches = []
        matched_keys = set()
        for rec in self._current_catalog():
            key = normalize_name(rec.get("name", ""))
            if key and key in files_by_name:
                matches.append((rec, files_by_name[key]))
                matched_keys.add(key)
        unmatched = [
            os.path.basename(path) for key, path in files_by_name.items()
            if key not in matched_keys
        ]
        return matches, sorted(unmatched)

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

    # ─── header buttons / mode toggle ───

    def _toggle_import_mode(self):
        if self._tools_mode == "import":
            self._close_tools_mode()
            return
        self._tools_title_lbl.setText(f"Importar {self._current_entity_label()}")
        self._tools_stack.setCurrentIndex(0)
        self._body_stack.setCurrentIndex(1)
        self._tools_mode = "import"

    def _on_export_choice(self, fmt: str):
        if fmt == "xlsx":
            self._export_xlsx()
            return
        mode = f"export_{fmt}"
        if self._tools_mode == mode:
            self._close_tools_mode()
            return
        self._template_fmt = fmt
        self._template_edit.setPlainText(self._build_entity_export(fmt))
        self._template_hint_lbl.setText(
            f"{len(self._current_catalog())} {self._current_entity_label().lower()} — clique em Salvar Arquivo para exportar, ou copie o texto abaixo."
        )
        self._tools_title_lbl.setText(
            f"Exportar {self._current_entity_label()} como JSON" if fmt == "json"
            else f"Exportar {self._current_entity_label()} como CSV"
        )
        self._tools_stack.setCurrentIndex(1)
        self._body_stack.setCurrentIndex(1)
        self._tools_mode = mode

    def _close_tools_mode(self):
        self._body_stack.setCurrentIndex(0)
        self._tools_mode = None

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

    def _build_entity_export(self, fmt: str) -> str:
        rows = self._export_rows(json_native=(fmt == "json"))
        if fmt == "json":
            import json
            return json.dumps(rows, ensure_ascii=False, indent=2)
        import csv
        import io
        fieldnames = list(self._current_fields().keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

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
