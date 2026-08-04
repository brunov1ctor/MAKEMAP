"""NPCDataMixin — reloading npc data from the repository, recomputing the
stat bar / Resumo Rápido donut+legend, and the Resumo Rápido card itself.
Mixed into NPCsPanel (see panel.py) — operates on self.* attributes
NPCsPanel owns; not meant to be instantiated on its own.

Mirrors src/layouts/panels/mobs/panel_data_mixin.py — stat chips swapped for
npc-appropriate ones (ativos/inativos/tipos/facções instead of boss/elite/
normal/elements/drops, since npcs has no rarity-tier or drops_json column).
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QWidget
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.donut_chart import DonutChart
from src.layouts.panels.npcs.categories import category_badge_color
from src.layouts.panels.npcs.panel_widgets import _SummaryCard, _ClickableHeader
from src.services.project_assets import resolve_asset_path

logger = logging.getLogger("MAKEMAP")


class NPCDataMixin:
    """Data loading (`_reload`) and the stat bar / Resumo Rápido
    recompute (`_recompute_stats`) + the Resumo Rápido card itself."""

    def _build_summary_card(self) -> QFrame:
        summary_card = _SummaryCard()
        self._summary_card = summary_card
        summary_card.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        summary_lay = QVBoxLayout(summary_card)
        summary_lay.setContentsMargins(10, 8, 10, 8)
        summary_lay.setSpacing(6)

        header = _ClickableHeader()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(
            "QFrame { background: transparent; border-radius: 4px; }"
            "QFrame:hover { background: rgba(255,255,255,0.05); }"
        )
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(0, 0, 0, 0)
        header_lay.setSpacing(4)
        self._summary_arrow = QLabel("▼")
        self._summary_arrow.setFixedWidth(10)
        self._summary_arrow.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 8px; background: transparent; border: none;")
        header_lay.addWidget(self._summary_arrow)
        summary_label = QLabel("RESUMO RÁPIDO")
        summary_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        header_lay.addWidget(summary_label)
        header_lay.addStretch()
        header.clicked.connect(self._toggle_summary_collapsed)
        summary_lay.addWidget(header)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(6)

        self._donut = DonutChart()
        donut_row = QHBoxLayout()
        donut_row.addStretch()
        donut_row.addWidget(self._donut)
        donut_row.addStretch()
        body_lay.addLayout(donut_row)

        legend_container = QWidget()
        self._summary_grid = QGridLayout(legend_container)
        self._summary_grid.setContentsMargins(0, 0, 0, 0)
        self._summary_grid.setSpacing(4)
        body_lay.addWidget(legend_container)

        summary_lay.addWidget(body)
        summary_card.set_body(body)
        summary_card.set_legend_container(legend_container)
        return summary_card

    def _toggle_summary_collapsed(self):
        collapsed = not self._summary_card.is_collapsed()
        self._summary_card.set_collapsed(collapsed)
        self._summary_arrow.setText("▶" if collapsed else "▼")

    def _reload(self):
        self._npcs = self._uow.npcs.get_all() if self._uow else []
        self._region_combo.blockSignals(True)
        current = self._region_combo.currentData()
        self._region_combo.clear()
        self._region_combo.addItem("Todas as Regiões", "")
        for zid, name in self._zones_provider():
            self._region_combo.addItem(name, zid)
        idx = self._region_combo.findData(current)
        self._region_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._region_combo.blockSignals(False)
        self._edit_panel.set_zone_options(self._zones_provider())
        self._reload_categories()
        # Resolved to absolute paths here (mirrors MobsPanel's own _reload)
        # — the DB stores image_path relative to the project dir, and
        # QPixmap() resolves a relative path against the process cwd, not
        # the project, so the Itens Fornecidos tile would otherwise
        # silently show no image.
        items = self._uow.items.get_all() if self._uow else []
        self._edit_panel.set_items_catalog([
            {**it, "image_path": resolve_asset_path(self._project_dir, it.get("image_path", ""))}
            for it in items
        ])
        self._recompute_stats()
        self._apply_filters()
        logger.info("Dados recarregados: %d npc(s)", len(self._npcs))

    def _recompute_stats(self):
        total = len(self._npcs)
        ativos = sum(1 for m in self._npcs if (m.get("status") or "ativo") == "ativo")
        inativos = total - ativos
        types = len({m.get("npc_type") for m in self._npcs if m.get("npc_type")})
        factions = len({m.get("faction") for m in self._npcs if m.get("faction")})
        favorites = sum(1 for m in self._npcs if m.get("favorite"))
        zones_used = len({m.get("zone_id") for m in self._npcs if m.get("zone_id")})

        values = {"total": total, "ativos": ativos, "inativos": inativos, "tipos": types,
                  "faccoes": factions, "favoritos": favorites, "zonas": zones_used}
        for key, chip in self._stat_chips.items():
            chip._value_label.setText(f"{values.get(key, 0):,}".replace(",", "."))

        roots = sorted(
            (c for c in self._all_categories if c.get("parent_id") is None),
            key=lambda c: (c.get("sort_order") or 0, c["name"]),
        )
        counts = {r["id"]: sum(1 for m in self._npcs if m.get("category") in self._descendant_ids(r["id"])) for r in roots}
        self._donut.set_data([(counts[r["id"]], category_badge_color(r["id"])) for r in roots], total)

        while self._summary_grid.count():
            item = self._summary_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, cat in enumerate(roots):
            count = counts[cat["id"]]
            pct = 100 * count / total if total else 0
            pct_text = f"{pct:.0f}%" if pct >= 1 or pct == 0 else "+1%"
            color = category_badge_color(cat["id"])

            row = QHBoxLayout()
            row.setSpacing(4)
            square = QLabel()
            square.setFixedSize(8, 8)
            square.setStyleSheet(f"background: {color}; border-radius: 2px;")
            row.addWidget(square)
            lbl = QLabel(f"{cat.get('icon') or '🧙'} {cat['name']}")
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 8px; background: transparent; border: none;")
            row.addWidget(lbl, 1)
            pct_lbl = QLabel(pct_text)
            pct_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; font-weight: bold; background: transparent; border: none;")
            row.addWidget(pct_lbl)

            cell = QWidget()
            cell.setLayout(row)
            self._summary_grid.addWidget(cell, i // 2, i % 2)
