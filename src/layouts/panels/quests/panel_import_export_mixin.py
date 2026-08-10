"""QuestsImportExportMixin — the Importar (JSON/CSV paste + Excel drop) /
Exportar (read-only JSON/CSV view + direct-to-file Excel) tools panel that
takes over the whole body of QuestsPanel while active — same shell as
dungeons/panel_import_export_mixin.py, but for a single entity (no
Dungeons/Construções-style toggle) like mobs/panel_import_export_mixin.py.

Mixed into QuestsPanel (see panel.py) — operates on self.* attributes that
panel owns (self._quests, self._uow, self._project_dir, self._body_stack,
...); not meant to be instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QTextEdit,
    QWidget, QStackedWidget, QScrollArea, QFileDialog,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.dungeons.constants import parse_json_records
from src.layouts.panels.items.import_export_constants import coerce_import_stats
from src.layouts.panels.quests.import_export_constants import (
    QUEST_TEMPLATE_FIELDS, QUEST_TEMPLATE_DOCS, QUEST_DB_COLUMNS,
    QUEST_JSON_FIELDS, QUEST_BOOL_FIELDS,
)
from src.layouts.panels.shared.import_export_helpers import (
    DropZone, normalize_blank_cells, read_json, read_csv, read_xlsx, import_button_row,
    build_tools_header, build_export_view_page,
)

logger = logging.getLogger("MAKEMAP")


class QuestsImportExportMixin:
    """The body's alternate page (see self._body_stack) — a header (title
    + ✕ close) above a stack of its own: page 0 is Importar (JSON/CSV
    paste, Excel drop), page 1 is a read-only export view."""

    # ─── tools panel shell ───

    def _build_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet("QFrame { background: rgba(255,255,255,0.03); border-radius: 8px; }")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        head_row, self._tools_title_lbl, _tools_close_btn = build_tools_header(self._close_tools_mode)
        outer.addLayout(head_row)

        self._tools_stack = QStackedWidget()

        # ── Page 0: Importar ──
        import_content = QWidget()
        import_lay = QVBoxLayout(import_content)
        import_lay.setContentsMargins(0, 0, 0, 0)
        import_lay.setSpacing(8)
        import_lay.addWidget(self._build_text_import_card(
            "JSON", "Cole uma lista JSON para criar várias quests de uma vez.", "json"))
        import_lay.addWidget(self._build_text_import_card(
            "CSV", "Cole uma lista CSV para criar várias quests de uma vez.", "csv"))
        import_lay.addWidget(self._build_excel_import_card())
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
        example = dict(QUEST_TEMPLATE_FIELDS)
        example["name"] = "Nova Quest"
        return example

    def _json_import_template(self) -> str:
        import json
        doc_lines = "\n".join(f"// {key}: {doc}" for key, doc in QUEST_TEMPLATE_DOCS)
        row_json = json.dumps(self._example_row(), ensure_ascii=False, indent=2)
        row_indented = "\n".join(f"  {line}" for line in row_json.splitlines())
        return f"{doc_lines}\n[\n{row_indented}\n]"

    def _csv_import_template(self) -> str:
        import csv
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(QUEST_TEMPLATE_FIELDS.keys()))
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
                    data = parse_json_records(text)
                else:
                    import csv
                    import io
                    data = [normalize_blank_cells(dict(row)) for row in csv.DictReader(io.StringIO(text))]
                    data = [d for d in data if d.get("name")]
                    if not data:
                        raise ValueError('Nenhum registro válido (cada um precisa de "name").')
            except ValueError as exc:
                error_lbl.setText(str(exc))
                error_lbl.show()
                return
            except Exception:
                logger.exception("Falha ao interpretar import de Quests (%s).", fmt)
                error_lbl.setText("Não foi possível interpretar o conteúdo — confira o formato.")
                error_lbl.show()
                return
            self._import_quest_records(data)
            logger.info("Criada(s) %d quest(s) via Importar (%s)", len(data), fmt)
            reset_to_template()
            self._close_tools_mode()

        row, _apply_btn = import_button_row(self._close_tools_mode, reset_to_template, do_apply)
        lay.addLayout(row)
        reset_to_template()
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
            import os
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
        self._import_quest_records(data)
        logger.info("Importada(s) quest(s) de %s", path)
        self._close_tools_mode()

    # ─── header buttons / mode toggle ───

    def _toggle_import_mode(self):
        if self._tools_mode == "import":
            self._close_tools_mode()
            return
        self._tools_title_lbl.setText("Importar Quests")
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
        self._template_edit.setPlainText(self._build_quest_export(fmt))
        self._template_hint_lbl.setText(
            f"{len(self._quests)} quest(s) — clique em Salvar Arquivo para exportar, ou copie o texto abaixo."
        )
        self._tools_title_lbl.setText("Exportar Quests como JSON" if fmt == "json" else "Exportar Quests como CSV")
        self._tools_stack.setCurrentIndex(1)
        self._body_stack.setCurrentIndex(1)
        self._tools_mode = mode

    def _close_tools_mode(self):
        self._body_stack.setCurrentIndex(0)
        self._tools_mode = None

    # ─── export ───

    def _export_rows(self, json_native: bool) -> list[dict]:
        """One row per quest, campo `region` resolvido pro NOME (não o
        region_id interno) pra ficar portável entre projetos — mesma
        lógica de "Item Requerido" nos outros editores."""
        import json
        fieldnames = list(QUEST_TEMPLATE_FIELDS.keys())
        defaults = QUEST_TEMPLATE_FIELDS
        rows = []
        for rec in self._quests:
            row = {}
            for key in fieldnames:
                if key == "region":
                    row["region"] = self._region_name(rec.get("region_id") or "")
                    continue
                db_col = QUEST_DB_COLUMNS[key]
                value = rec.get(db_col, defaults[key])
                if key in QUEST_JSON_FIELDS:
                    if json_native:
                        try:
                            value = json.loads(value) if isinstance(value, str) else (value if value is not None else defaults[key])
                        except (json.JSONDecodeError, TypeError):
                            value = defaults[key]
                    elif not isinstance(value, str):
                        value = json.dumps(value, ensure_ascii=False)
                elif key in QUEST_BOOL_FIELDS:
                    value = bool(value)
                row[key] = value
            rows.append(row)
        return rows

    def _build_quest_export(self, fmt: str) -> str:
        rows = self._export_rows(json_native=(fmt == "json"))
        if fmt == "json":
            import json
            return json.dumps(rows, ensure_ascii=False, indent=2)
        import csv
        import io
        fieldnames = list(QUEST_TEMPLATE_FIELDS.keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    def _on_save_export_file(self):
        fmt = self._template_fmt
        ext = "json" if fmt == "json" else "csv"
        file_filter = "JSON (*.json)" if fmt == "json" else "CSV (*.csv)"
        path, _selected = QFileDialog.getSaveFileName(self, "Salvar Exportação de Quests", f"quests.{ext}", file_filter)
        if not path:
            return
        if not path.lower().endswith(f".{ext}"):
            path += f".{ext}"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self._template_edit.toPlainText())
        logger.info("Exportação de quests salva: %s (%s, %d registro(s))", path, fmt, len(self._quests))

    def _export_xlsx(self):
        path, _selected = QFileDialog.getSaveFileName(
            self, "Exportar Quests (Excel)", "quests.xlsx", "Planilha Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        from openpyxl import Workbook

        fieldnames = list(QUEST_TEMPLATE_FIELDS.keys())
        rows = self._export_rows(json_native=False)
        wb = Workbook()
        ws = wb.active
        ws.title = "Quests"
        ws.append(fieldnames)
        for row in rows:
            ws.append([row[k] for k in fieldnames])
        wb.save(path)
        logger.info("Quests exportadas para %s (%d linha(s))", path, len(rows))

    def _export_xlsx_blank_template(self):
        path, _selected = QFileDialog.getSaveFileName(
            self, "Baixar Template de Quests (Excel)", "quests_template.xlsx", "Planilha Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        import json
        from openpyxl import Workbook

        fieldnames = list(QUEST_TEMPLATE_FIELDS.keys())
        example = self._example_row()
        wb = Workbook()
        ws = wb.active
        ws.title = "Quests"
        ws.append(fieldnames)
        ws.append([json.dumps(example[k], ensure_ascii=False) if k in QUEST_JSON_FIELDS else example.get(k, "")
                   for k in fieldnames])
        wb.save(path)
        logger.info("Template Excel de quests baixado: %s", path)

    # ─── import (bulk create) ───

    def _import_quest_records(self, records: list[dict]) -> str | None:
        """The actual quest-create loop, used by every Importar card. Cada
        linha vira uma quest nova (Importar sempre CRIA, nunca atualiza uma
        existente — mesmo comportamento dos outros módulos)."""
        if not self._uow:
            return None
        import json
        import uuid
        codes = [q.get("code", "") for q in self._quests]
        last_id = None
        for rec in records:
            if not isinstance(rec, dict) or not rec.get("name"):
                continue
            quest_id = str(uuid.uuid4())
            code = self._next_code("QST_", codes)
            codes.append(code)

            region_name = str(rec.get("region") or "").strip()
            region_id = self._region_id_by_name(region_name) if region_name else None

            # Toda chave ausente cai no default do QUEST_TEMPLATE_FIELDS (ex.:
            # status="Rascunho", priority="Média"), não no default bruto da
            # coluna no schema.py ("rascunho"/"media" minúsculo) — os dois
            # nunca combinaram, e status/priority são comparados por
            # igualdade de texto no filtro da lista e no combo de status do
            # cabeçalho, então um valor com case diferente silenciosamente
            # não bate com nenhuma opção.
            fields = {}
            for key, db_col in QUEST_DB_COLUMNS.items():
                # "name"/"region" são passados explicitamente pro create()
                # abaixo — incluí-los aqui também duplicaria o argumento.
                if db_col is None or key in ("name", "region"):
                    continue
                fields[db_col] = rec[key] if key in rec else QUEST_TEMPLATE_FIELDS[key]
            fields = coerce_import_stats(fields, tuple(QUEST_DB_COLUMNS[k] for k in QUEST_JSON_FIELDS),
                                          tuple(QUEST_DB_COLUMNS[k] for k in QUEST_BOOL_FIELDS))
            for json_key in QUEST_JSON_FIELDS:
                db_col = QUEST_DB_COLUMNS[json_key]
                if db_col in fields:
                    fields[db_col] = json.dumps(fields[db_col], ensure_ascii=False) if not isinstance(fields[db_col], str) else fields[db_col]
            for int_key in ("level_req", "level_max", "time_limit_seconds"):
                if int_key in fields and fields[int_key] is not None:
                    fields[int_key] = int(float(fields[int_key]))

            self._uow.quests.create(
                id=quest_id, code=code,
                name=str(rec.get("name") or "Nova Quest"),
                region_id=region_id,
                **fields,
            )
            last_id = quest_id
        self._reload_quests(select_id=last_id)
        return last_id
