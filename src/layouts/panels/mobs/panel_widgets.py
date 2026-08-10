"""Standalone widget classes used by MobsPanel — re-exported from the
shared implementation (see shared/entity_panel/panel_widgets.py), which
MobsPanel and NPCsPanel share byte-for-byte: nothing here ever read/wrote
MobsPanel internals, so there was no entity-specific behavior to keep once
the duplicate was found (see npcs/panel_widgets.py for the same shim)."""

from __future__ import annotations

from src.layouts.panels.shared.entity_panel.panel_widgets import (
    _rounded_thumbnail,
    _InlineNameEdit,
    _SidebarRow,
    _DropZone,
    _ClickableHeader,
    _SummaryCard,
)

__all__ = [
    "_rounded_thumbnail", "_InlineNameEdit", "_SidebarRow", "_DropZone",
    "_ClickableHeader", "_SummaryCard",
]
