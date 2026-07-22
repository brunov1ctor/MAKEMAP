"""ImportExportMixin — the Importar (drag-and-drop) / Exportar (editable
template + Excel) tools panel that takes over the right column while
active. Mixed into MobsPanel (see panel.py) — operates on self.*
attributes MobsPanel owns; not meant to be instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QTextEdit,
    QPushButton, QWidget, QStackedWidget, QFileDialog,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.mob_edit_panel import MobEditPanel
from src.layouts.panels.mobs.panel_widgets import _DropZone
from src.layouts.panels.mobs.panel_helpers import _TEMPLATE_EXAMPLE, _TEMPLATE_FIELD_DOCS, _parse_mobs_json

logger = logging.getLogger("MAKEMAP")


class ImportExportMixin:
    """The right column's alternate page (see self._right_stack) — a
    header (title + ✕ close) above a small stack of its own: page 0 is
    the drag-and-drop zone (Importar), page 1 is the editable JSON/CSV
    template (Exportar)."""

    def _build_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(f"QFrame {{ background: rgba(255,255,255,0.03); border-radius: 8px; }}")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        head_row = QHBoxLayout()
        self._tools_title_lbl = QLabel("")
        self._tools_title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        head_row.addWidget(self._tools_title_lbl, 1)
        tools_close_btn = QToolButton()
        tools_close_btn.setText("✕")
        tools_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tools_close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 12px; padding: 2px 6px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        tools_close_btn.clicked.connect(self._close_tools_mode)
        head_row.addWidget(tools_close_btn)
        outer.addLayout(head_row)

        self._tools_stack = QStackedWidget()

        # ── Page 0: drag-and-drop import zone ──
        self._drop_zone = _DropZone()
        self._drop_zone.file_chosen.connect(self._on_file_dropped)
        self._tools_stack.addWidget(self._drop_zone)

        # ── Page 1: editable JSON/CSV template ──
        template_page = QWidget()
        template_lay = QVBoxLayout(template_page)
        template_lay.setContentsMargins(0, 0, 0, 0)
        template_lay.setSpacing(6)

        self._template_hint_lbl = QLabel("")
        self._template_hint_lbl.setWordWrap(True)
        self._template_hint_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        template_lay.addWidget(self._template_hint_lbl)

        self._template_edit = QTextEdit()
        self._template_edit.setStyleSheet(f"""
            QTextEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-family: Consolas, monospace;
                background: rgba(0,0,0,0.2); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 6px; }}
        """)
        template_lay.addWidget(self._template_edit, 1)

        self._template_error_lbl = QLabel("")
        self._template_error_lbl.setWordWrap(True)
        self._template_error_lbl.setStyleSheet(f"color: {Colors.ERROR}; font-size: 9px; background: transparent; border: none;")
        self._template_error_lbl.hide()
        template_lay.addWidget(self._template_error_lbl)

        template_btn_row = QHBoxLayout()
        template_btn_row.addStretch()
        template_cancel_btn = QPushButton("Cancelar")
        template_cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        template_cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY}; border: none;
                border-radius: 6px; padding: 6px 12px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        template_cancel_btn.clicked.connect(self._close_tools_mode)
        template_btn_row.addWidget(template_cancel_btn)
        template_apply_btn = QPushButton("Aplicar")
        template_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        template_apply_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 6px 14px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        template_apply_btn.clicked.connect(self._apply_template)
        template_btn_row.addWidget(template_apply_btn)
        template_lay.addLayout(template_btn_row)

        self._tools_stack.addWidget(template_page)
        outer.addWidget(self._tools_stack, 1)

        panel.setMinimumWidth(MobEditPanel.PANEL_WIDTH)
        return panel

    def _toggle_import_mode(self):
        if self._tools_mode == "import":
            self._close_tools_mode()
            return
        self._tools_title_lbl.setText("Importar Mobs")
        self._tools_stack.setCurrentIndex(0)
        self._right_stack.setCurrentIndex(1)
        self._tools_mode = "import"

    def _on_export_choice(self, fmt: str):
        if fmt == "xlsx":
            # Not text-editable in-panel (it's a binary spreadsheet), so
            # this generates a template FILE directly instead of taking
            # over the right panel — see _export_xlsx_template.
            self._export_xlsx_template()
            return
        mode = f"export_{fmt}"
        if self._tools_mode == mode:
            self._close_tools_mode()
            return
        self._template_fmt = fmt
        self._template_edit.setPlainText(self._build_mob_template(fmt))
        self._template_error_lbl.hide()
        self._template_hint_lbl.setText(
            "Edite o(s) mob(s) abaixo (duplique o bloco { ... } para adicionar mais de um) e clique em Aplicar para criá-los."
            if fmt == "json" else
            "Edite ou adicione linhas — uma por mob — e clique em Aplicar. Não apague a primeira linha (cabeçalho)."
        )
        self._tools_title_lbl.setText("Exportar como JSON" if fmt == "json" else "Exportar como CSV")
        self._tools_stack.setCurrentIndex(1)
        self._right_stack.setCurrentIndex(1)
        self._tools_mode = mode

    def _close_tools_mode(self):
        self._right_stack.setCurrentIndex(0)
        self._tools_mode = None

    def _build_mob_template(self, fmt: str) -> str:
        valid_categories = ", ".join(
            f"{c['id']} ({c['name']})" for c in sorted(self._all_categories, key=lambda c: c["name"])
        ) or "nenhuma ainda — crie uma no explorador à esquerda"
        if fmt == "json":
            import json
            doc_lines = "\n".join(f"// {key}: {doc}" for key, doc in _TEMPLATE_FIELD_DOCS)
            cat_line = f"// Categorias disponíveis: {valid_categories}"
            row_json = json.dumps(_TEMPLATE_EXAMPLE, ensure_ascii=False, indent=2)
            row_indented = "\n".join(f"  {line}" for line in row_json.splitlines())
            return f"{doc_lines}\n{cat_line}\n[\n{row_indented}\n]"
        # csv
        import csv
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(_TEMPLATE_EXAMPLE.keys()))
        writer.writeheader()
        writer.writerow(_TEMPLATE_EXAMPLE)
        return buf.getvalue()

    def _apply_template(self):
        if not self._uow:
            return
        text = self._template_edit.toPlainText()
        try:
            if self._template_fmt == "json":
                data = _parse_mobs_json(text)
            else:
                import csv
                import io
                data = [self._normalize_blank_cells(dict(row)) for row in csv.DictReader(io.StringIO(text))]
        except ValueError as exc:
            self._template_error_lbl.setText(str(exc))
            self._template_error_lbl.show()
            return
        except Exception:
            logger.exception("Falha ao interpretar o template de mobs.")
            self._template_error_lbl.setText("Não foi possível interpretar o conteúdo — confira o formato.")
            self._template_error_lbl.show()
            return
        imported = self._import_mob_dicts(data)
        if imported == 0:
            self._template_error_lbl.setText('Nenhum mob válido encontrado (o campo "name" é obrigatório).')
            self._template_error_lbl.show()
            return
        logger.info("Criados %d mob(s) a partir do template (%s)", imported, self._template_fmt)
        self._reload()
        self._close_tools_mode()

    def _on_file_dropped(self, path: str):
        if not self._uow:
            return
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        reader = {"json": self._read_json, "csv": self._read_csv, "xlsx": self._read_xlsx}.get(suffix)
        if reader is None:
            logger.warning("Formato de arquivo não suportado para import: %s", path)
            return
        try:
            data = reader(path)
        except Exception:
            logger.exception("Falha ao ler arquivo de importação: %s", path)
            return
        imported = self._import_mob_dicts(data)
        logger.info("Importados %d mobs de %s", imported, path)
        self._reload()
        self._close_tools_mode()

    def _export_xlsx_template(self):
        """Excel's own template — not the user's current mobs, a blank
        skeleton with all field headers, one example row, and a
        Categorias reference sheet with a dropdown data-validation on the
        "category" column restricted to real category ids, so filling
        this in by hand can't produce a typo'd/nonexistent category."""
        path, _selected = QFileDialog.getSaveFileName(
            self, "Exportar Template de Mobs (Excel)", "mobs_template.xlsx", "Planilha Excel (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        from openpyxl import Workbook
        from openpyxl.worksheet.datavalidation import DataValidation

        fieldnames = list(_TEMPLATE_EXAMPLE.keys())
        wb = Workbook()
        ws = wb.active
        ws.title = "Mobs"
        ws.append(fieldnames)
        ws.append([_TEMPLATE_EXAMPLE.get(k, "") for k in fieldnames])

        categories = sorted(self._all_categories, key=lambda c: c["name"])
        cats_ws = wb.create_sheet("Categorias")
        cats_ws.append(["id", "nome"])
        for c in categories:
            cats_ws.append([c["id"], c["name"]])

        if categories and "category" in fieldnames:
            col_letter = ws.cell(row=1, column=fieldnames.index("category") + 1).column_letter
            dv = DataValidation(type="list", formula1=f"=Categorias!$A$2:$A${len(categories) + 1}", allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{col_letter}2:{col_letter}1000")

        wb.save(path)
        logger.info("Template Excel de mobs exportado para %s", path)

    def _import_mob_dicts(self, data) -> int:
        """Shared by the drop zone (any of the 3 file formats) and the
        JSON/CSV template's Aplicar button alike — each just parses its
        input into a list[dict] shaped like a mob row and hands it here,
        so this validation+create logic exists once."""
        if not isinstance(data, list):
            logger.warning("Arquivo de importação inválido: esperada uma lista de mobs.")
            return 0
        known_columns = self._known_mob_columns()
        imported = 0
        for entry in data:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            fields = {k: v for k, v in entry.items()
                      if k not in ("id", "created_at", "updated_at") and (known_columns is None or k in known_columns)}
            # Importing/creating while browsing inside a folder files every
            # mob under that folder directly — like dropping files into a
            # directory in a file explorer — instead of whatever category
            # (or none) the source data happened to specify.
            if self._current_dir_id is not None:
                fields["category"] = self._current_dir_id
            self._uow.mobs.create(**fields)
            imported += 1
        logger.info("Mobs importados: %d (categoria=%s)", imported, self._current_dir_id)
        return imported

    def _known_mob_columns(self) -> set[str] | None:
        """The real mobs columns via PRAGMA, not `self._mobs[0].keys()` —
        that fallback silently disabled column filtering (returned None)
        whenever the project had zero mobs yet, exactly the situation a
        first-ever CSV/Excel import (far more likely than JSON to carry
        stray hand-edited columns) would hit."""
        if not self._uow:
            return None
        try:
            return set(self._uow.mobs.db.table_columns(self._uow.mobs.TABLE))
        except Exception:
            logger.exception("Falha ao introspectar colunas de mobs; import sem filtro de colunas.")
            return None

    # ─── Format-specific readers (file -> list[dict]) ───
    # resistances/drops_json are already JSON-encoded TEXT columns in the
    # DB — CSV/Excel just carry that same string verbatim in one cell, same
    # as JSON, so nothing special is needed to pass them through.

    def _read_json(self, path: str) -> list:
        import json
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_csv(self, path: str) -> list[dict]:
        import csv
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            return [self._normalize_blank_cells(dict(row)) for row in csv.DictReader(f)]

    @staticmethod
    def _normalize_blank_cells(row: dict) -> dict:
        """CSV/Excel have no NULL — an unset value (None in the DB, e.g.
        mobs.region_id which has a foreign key) round-trips as a blank
        cell (empty string from csv, None from openpyxl for a truly empty
        cell) instead, which then fails that FK constraint on reimport
        (an empty string isn't NULL, so it doesn't get the FK's implicit
        NULL bypass). A blank cell means "not set", same as it did before
        export, so both forms are normalized to None here rather than
        passed through as a literal empty string."""
        return {k: (None if v in ("", None) else v) for k, v in row.items()}

    def _read_xlsx(self, path: str) -> list[dict]:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else "" for c in next(rows, [])]
        return [
            self._normalize_blank_cells({header[i]: cell for i, cell in enumerate(row) if i < len(header)})
            for row in rows
        ]
