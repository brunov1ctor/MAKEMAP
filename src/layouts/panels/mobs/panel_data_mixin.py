"""MobDataMixin — reloading mob data from the repository, recomputing the
stat bar / Resumo Rápido donut+legend, and the Resumo Rápido card itself.
Mixed into MobsPanel (see panel.py) — operates on self.* attributes
MobsPanel owns; not meant to be instantiated on its own.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QWidget

from src.styles.tokens import Colors
from src.layouts.panels.mobs.donut_chart import DonutChart
from src.layouts.panels.mobs.panel_helpers import _category_color
from src.layouts.panels.mobs.panel_widgets import _SummaryCard

logger = logging.getLogger("MAKEMAP")


class MobDataMixin:
    """Data loading (`_reload`) and the stat bar / Resumo Rápido
    recompute (`_recompute_stats`) + the Resumo Rápido card itself."""

    def _build_summary_card(self) -> QFrame:
        """"Resumo Rápido" — its own independent bordered card, a sibling
        of the category list (not nested inside it). The legend below the
        donut hides itself on a short window instead of forcing the card
        to stay a minimum size — see _SummaryCard."""
        summary_card = _SummaryCard()
        self._summary_card = summary_card
        summary_card.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        summary_lay = QVBoxLayout(summary_card)
        summary_lay.setContentsMargins(10, 8, 10, 8)
        summary_lay.setSpacing(6)

        summary_label = QLabel("RESUMO RÁPIDO")
        summary_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        summary_lay.addWidget(summary_label)

        self._donut = DonutChart()
        donut_row = QHBoxLayout()
        donut_row.addStretch()
        donut_row.addWidget(self._donut)
        donut_row.addStretch()
        summary_lay.addLayout(donut_row)

        legend_container = QWidget()
        self._summary_grid = QGridLayout(legend_container)
        self._summary_grid.setContentsMargins(0, 0, 0, 0)
        self._summary_grid.setSpacing(4)
        summary_lay.addWidget(legend_container)
        summary_card.set_legend_container(legend_container)
        return summary_card

    def _reload(self):
        self._mobs = self._uow.mobs.get_all() if self._uow else []
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
        categories = self._reload_categories()
        self._edit_panel.set_category_options(categories)
        self._edit_panel.set_items_catalog(self._uow.items.get_all() if self._uow else [])
        self._recompute_stats()
        self._apply_filters()
        logger.info("Dados recarregados: %d mob(s)", len(self._mobs))

    def _recompute_stats(self):
        total = len(self._mobs)
        boss = sum(1 for m in self._mobs if m.get("rarity") == "boss")
        elite = sum(1 for m in self._mobs if m.get("rarity") == "elite")
        normal = total - boss - elite
        elements = len({m.get("element") for m in self._mobs if m.get("element")})
        drops = 0
        for m in self._mobs:
            import json
            try:
                drops += len(json.loads(m.get("drops_json") or "[]"))
            except (ValueError, TypeError):
                pass
        zones_used = len({m.get("zone_id") for m in self._mobs if m.get("zone_id")})

        values = {"total": total, "boss": boss, "elite": elite, "normal": normal,
                  "elements": elements, "drops": drops, "zones": zones_used}
        for key, chip in self._stat_chips.items():
            chip._value_label.setText(f"{values.get(key, 0):,}".replace(",", "."))

        for key, row in self._sidebar_rows.items():
            if key == "todos":
                row.set_count(total)
            elif key == "favoritos":
                row.set_count(sum(1 for m in self._mobs if m.get("favorite")))

        # Resumo rápido — donut + 2-column legend, counts by top-level
        # category (whatever's created in the category explorer), not
        # rarity. A mob nested several folders deep still counts toward
        # its top-level ancestor — same recursive semantics as the "Tipo"
        # filter combo and the folder cards' own count badges.
        roots = sorted(
            (c for c in self._all_categories if c.get("parent_id") is None),
            key=lambda c: (c.get("sort_order") or 0, c["name"]),
        )
        counts = {r["id"]: sum(1 for m in self._mobs if m.get("category") in self._descendant_ids(r["id"])) for r in roots}
        self._donut.set_data([(counts[r["id"]], _category_color(i)) for i, r in enumerate(roots)], total)

        while self._summary_grid.count():
            item = self._summary_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, cat in enumerate(roots):
            count = counts[cat["id"]]
            pct = 100 * count / total if total else 0
            pct_text = f"{pct:.0f}%" if pct >= 1 or pct == 0 else "+1%"
            color = _category_color(i)

            row = QHBoxLayout()
            row.setSpacing(4)
            square = QLabel()
            square.setFixedSize(8, 8)
            square.setStyleSheet(f"background: {color}; border-radius: 2px;")
            row.addWidget(square)
            lbl = QLabel(f"{cat.get('icon') or '📁'} {cat['name']}")
            lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 8px; background: transparent; border: none;")
            row.addWidget(lbl, 1)
            pct_lbl = QLabel(pct_text)
            pct_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8px; font-weight: bold; background: transparent; border: none;")
            row.addWidget(pct_lbl)

            cell = QWidget()
            cell.setLayout(row)
            self._summary_grid.addWidget(cell, i // 2, i % 2)
