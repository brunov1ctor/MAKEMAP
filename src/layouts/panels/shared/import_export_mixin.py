"""EntityModeImportExportMixin — the card-building/export/import mechanics
shared by any "toggle between N entity kinds" Importar/Exportar tools panel
(first written for dungeons/panel_import_export_mixin.py's
DungeonsImportExportMixin and items/panel_import_export_mixin.py's
ItemsImportExportMixin, which carried a ~500-line near-verbatim copy of
this ON TOP OF their own `_current_*` entity-mode protocol — see those two
files' docstrings).

This class does NOT replace that `_current_*` protocol — it's built on top
of it, same as the rest of each concrete mixin. A subclass must still
provide: `_current_entity_label`, `_current_catalog`, `_current_fields`,
`_current_required_keys`, `_current_import_fn`, `_current_repo`,
`_current_asset_folder`, `_json_import_template`, `_csv_import_template`,
`_export_rows`, `_export_xlsx_blank_template`, `_image_folder_hint_text`
(the one genuinely-different string in `_build_image_folder_import_card` —
"...como as dungeons/construções..." vs "...como os itens/habilidades...")
plus the self.* state each panel.py owns (`_uow`, `_body_stack`,
`_tools_mode`, `_tools_stack`, `_tools_title_lbl`, `_template_fmt`,
`_template_edit`, `_staged_image_files`, and — only if the subclass has
per-entity-mode staged state to clear on toggle —
`_entity_mode_reset_callbacks`, checked with getattr so a subclass that
doesn't have the concept, like a future single-entity mixin, can just not
define it).

Quests' own panel_import_export_mixin.py deliberately does NOT subclass
this: it has no entity-mode toggle, no "Imagens (pasta)" card, and every
log/dialog string is phrased in Portuguese for a single feminine-gendered
entity ("Importada(s) quest(s)...", not "Importado(s) %s...") rather than
built from `_current_entity_label()` — forcing it through this shared base
would mean adding one hook per method just to keep its wording exactly as
it is today, which isn't worth the behavior risk for a screen this size.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QTextEdit,
    QPushButton, QFileDialog,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.shared.import_export_helpers import (
    DropZone, normalize_name, index_files_by_stem, normalize_blank_cells,
    read_json, read_csv, read_xlsx, import_button_row,
)

logger = logging.getLogger("MAKEMAP")

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


class EntityModeImportExportMixin:
    """Card-building + import/export mechanics shared by DungeonsImportExportMixin
    and ItemsImportExportMixin — everything here dispatches through the
    `_current_*` protocol each concrete mixin already implements, so it
    reads/writes the right entity mode automatically."""

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

    # ─── Importar cards (JSON/CSV paste, Excel drop) ───

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
                    # Local import: dungeons.constants transitively imports
                    # dungeons.panel -> dungeons.panel_import_export_mixin ->
                    # this module, so a module-level import here would be
                    # circular. parse_json_records itself has zero coupling
                    # to any panel's state (see its docstring), so deferring
                    # the import to call time is free.
                    from src.layouts.panels.dungeons.constants import parse_json_records
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

        hint_lbl = QLabel(self._image_folder_hint_text())
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

    # ─── export ───

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
