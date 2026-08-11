"""LorePanel — o módulo em tela cheia "Lore".

Duas colunas lado a lado dentro de um splitter horizontal (mais simples que
Quests: sem abas de conteúdo, o editor inteiro é uma coluna só):

    ┌─── lista ───┬──────────── editor ────────────┐
    │  entradas   │  Título/Categoria/Autor, Tags,  │
    │  de lore    │  Resumo, Conteúdo (rich text)   │
    └─────────────┴─────────────────────────────────┘

mais uma barra de estatísticas no rodapé.
"""

from __future__ import annotations

import logging
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from src.styles.tokens import Colors
from src.components.live_splitter import LiveSplitter
from src.layouts.panels.mobs.panel_helpers import _stat_chip
from src.layouts.panels.lore.record_list import RecordListColumn
from src.layouts.panels.lore.editor_panel import LoreEditorPanel
from src.layouts.panels.lore.constants import panel_frame_style, CATEGORY_LABELS, json_list

logger = logging.getLogger("MAKEMAP")

# As 5 categorias com contador próprio no rodapé, na mesma ordem/seleção da
# tela de referência — Evento e Criatura ficam só no filtro da lista, sem
# chip dedicado (a imagem de referência também só mostra 5).
_FEATURED_CATEGORIES = [
    ("reinos", "👑", "Reino", "Reinos"),
    ("faccoes", "🚩", "Facção", "Facções"),
    ("personagens", "🧑", "Personagem", "Personagens"),
    ("locais", "🗺", "Local", "Locais"),
    ("artefatos", "🏺", "Artefato", "Artefatos"),
]


class LorePanel(QWidget):
    """Módulo em tela cheia de Lore."""

    closed = Signal()
    mention_open_requested = Signal(str, str)  # entity_type, entity_id

    def __init__(self, uow, project_dir=None, parent=None):
        super().__init__(parent)
        self._uow = uow
        self._project_dir = project_dir
        self._entries: list[dict] = []
        self._current_id = ""

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_entry)

        self._build_ui()
        self._reload_entries()

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

        outer.addLayout(self._build_stats_row())

        self._splitter = LiveSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(8)
        self._splitter.addWidget(self._build_list_column())
        self._editor = LoreEditorPanel()
        self._editor.changed.connect(self._save_timer.start)
        self._editor.duplicate_requested.connect(self._on_duplicate_entry)
        self._editor.delete_requested.connect(self._on_delete_current_entry)
        self._editor.mention_clicked.connect(self.mention_open_requested.emit)
        self._splitter.addWidget(self._editor)
        self._splitter.setSizes([280, 720])
        outer.addWidget(self._splitter, 1)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel("📖")
        icon.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        header.addWidget(icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("LORE")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 14pt; font-weight: bold; background: transparent; border: none;")
        subtitle = QLabel("Gerencie a história e o conhecimento do seu universo.")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

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

    def _build_stats_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._stat_chips: dict[str, QFrame] = {}
        base = [
            ("total", "📖", "Entradas de Lore"),
            ("categorias", "🏷", "Categorias"),
            ("tags", "🔖", "Tags utilizadas"),
            ("autores", "🧑‍💻", "Autores"),
        ]
        for key, icon_c, label in base + [(k, i, lbl) for k, i, _c, lbl in _FEATURED_CATEGORIES]:
            chip = _stat_chip(icon_c, "0", label)
            self._stat_chips[key] = chip
            row.addWidget(chip)
        row.addStretch()
        return row

    def _build_list_column(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("subpanel")
        frame.setStyleSheet(panel_frame_style())
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setMinimumWidth(220)
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(8)

        new_btn = QPushButton("+  Nova Entrada")
        new_btn.setFixedHeight(28)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{ background: {Colors.ACCENT}; color: #08131F; border: none;
                border-radius: 6px; padding: 0 10px; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        new_btn.clicked.connect(self._on_new_entry)
        column.addWidget(new_btn)

        self._entry_list = RecordListColumn(
            "Entradas de Lore", "Buscar no lore...",
        )
        self._entry_list.selected.connect(self._on_entry_selected)
        self._entry_list.delete_requested.connect(self._on_entry_delete)
        column.addWidget(self._entry_list, 1)
        return frame

    # ── dados ──

    def _entry_row(self, e: dict) -> dict:
        return {
            "id": e["id"],
            "name": e.get("title") or "—",
            "subtitle": e.get("summary") or "",
            "icon": "📖",
            "category": e.get("category") or "",
            "code": e.get("code") or "",
            "updated_at": e.get("updated_at") or "",
        }

    def _refresh_entry_list_view(self):
        self._entry_list.set_records([self._entry_row(e) for e in self._entries])

    def _refresh_stats(self):
        if not hasattr(self, "_stat_chips"):
            return
        total = len(self._entries)
        categories = {e.get("category") for e in self._entries if e.get("category")}
        tags = set()
        for e in self._entries:
            tags.update(json_list(e.get("tags_json")))
        authors = {e.get("author") for e in self._entries if e.get("author")}

        self._stat_chips["total"]._value_label.setText(str(total))
        self._stat_chips["categorias"]._value_label.setText(str(len(categories)))
        self._stat_chips["tags"]._value_label.setText(str(len(tags)))
        self._stat_chips["autores"]._value_label.setText(str(len(authors)))
        for key, _icon, category_name, _label in _FEATURED_CATEGORIES:
            count = sum(1 for e in self._entries if e.get("category") == category_name)
            self._stat_chips[key]._value_label.setText(str(count))

    def _build_mention_catalog(self) -> list[dict]:
        """Flat list combining every mentionable entity type for the "@"
        popup in the Conteúdo field — RichTextEditor stays entity-agnostic,
        this is the one place that actually knows the shapes of
        Mobs/NPCs/Itens/Habilidades/Quests/Dungeons."""
        if not self._uow:
            return []
        sources = [
            ("mob", "👹", self._uow.mobs.get_all()),
            ("npc", "🧙", self._uow.npcs.get_all()),
            ("item", "⚔", self._uow.items.get_all()),
            ("skill", "✨", self._uow.skills.get_all()),
            ("quest", "📜", self._uow.quests.get_all()),
            ("dungeon", "🏰", self._uow.dungeons.get_all()),
        ]
        catalog = []
        for entity_type, icon, rows in sources:
            for row in rows:
                catalog.append({
                    "type": entity_type, "id": row["id"],
                    "name": row.get("name") or "—", "icon": icon,
                })
        return catalog

    def _reload_entries(self, select_id: str | None = None):
        self._entries = self._uow.lore.get_all() if self._uow else []
        self._entries.sort(key=lambda e: (e.get("title") or ""))
        self._refresh_entry_list_view()
        self._refresh_stats()
        self._editor.set_mention_catalog(self._build_mention_catalog())

        if select_id:
            self._on_entry_selected(select_id)
        elif self._current_id and self._entry_by_id(self._current_id):
            self._entry_list.select(self._current_id)
        elif self._entries:
            self._on_entry_selected(self._entries[0]["id"])
        else:
            self._current_id = ""
            self._editor.set_empty()

    def _entry_by_id(self, entry_id: str) -> dict | None:
        return next((e for e in self._entries if e["id"] == entry_id), None)

    def _on_entry_selected(self, entry_id: str):
        record = self._entry_by_id(entry_id)
        if not record:
            return
        self._current_id = entry_id
        self._entry_list.select(entry_id)
        self._editor.load(record)

    def _on_new_entry(self):
        if not self._uow:
            return
        entry_id = str(uuid.uuid4())
        self._uow.lore.create(
            id=entry_id,
            code=self._next_code("LORE-", [e.get("code", "") for e in self._entries]),
            title="Nova Entrada", category=CATEGORY_LABELS[0],
            tags_json="[]", summary="", content_html="", author="",
        )
        self._reload_entries(select_id=entry_id)
        logger.info("Nova entrada de lore criada: id=%s", entry_id)

    def _on_duplicate_entry(self):
        if not self._uow or not self._current_id:
            return
        source = self._entry_by_id(self._current_id)
        if not source:
            return
        entry_id = str(uuid.uuid4())
        self._uow.lore.create(
            id=entry_id,
            code=self._next_code("LORE-", [e.get("code", "") for e in self._entries]),
            title=f"{source.get('title', '')} (cópia)", category=source.get("category", ""),
            tags_json=source.get("tags_json", "[]"), summary=source.get("summary", ""),
            content_html=source.get("content_html", ""), author=source.get("author", ""),
        )
        self._reload_entries(select_id=entry_id)

    def _save_entry(self):
        if not self._uow or not self._current_id:
            return
        values = self._editor.collect()
        self._uow.lore.update(self._current_id, **values)
        record = self._entry_by_id(self._current_id)
        if record:
            record.update(values)
        self._refresh_entry_list_view()
        self._refresh_stats()
        self._entry_list.select(self._current_id)

    def _flush_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_entry()

    def flush_pending_saves(self):
        """Chamado pelo MenuViewMediator antes de trocar/fechar o painel —
        evita perder uma edição debounced em andamento (mesmo padrão de
        QuestsPanel.flush_pending_saves)."""
        self._flush_save()

    def _on_close_clicked(self):
        self.flush_pending_saves()
        self.closed.emit()

    def _on_entry_delete(self, entry_id: str):
        if not self._uow:
            return
        if self._current_id == entry_id:
            self._save_timer.stop()
            self._current_id = ""
        self._uow.lore.delete(entry_id)
        self._reload_entries()
        logger.info("Entrada de lore excluída: id=%s", entry_id)

    def _on_delete_current_entry(self):
        if self._current_id:
            self._on_entry_delete(self._current_id)

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
