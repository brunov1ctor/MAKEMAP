"""CategoryEditPanel — full create/edit panel for a single npc_categories
folder. Implementation lives in shared/entity_panel/category_edit_panel.py
(byte-identical to mobs/category_edit_panel.py except which emoji a
brand-new category defaults to) — this module just supplies that one
entity-specific default (🧙, the DB default for npc_categories.icon) and
re-exports ICON_CHOICES for any code that imports it from here."""

from __future__ import annotations

from src.layouts.panels.shared.entity_panel.category_edit_panel import (
    CategoryEditPanel as _BaseCategoryEditPanel,
    ICON_CHOICES,
)


class CategoryEditPanel(_BaseCategoryEditPanel):
    DEFAULT_ICON = "🧙"
