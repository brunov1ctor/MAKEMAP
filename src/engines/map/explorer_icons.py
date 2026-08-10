"""Default Explorer-panel icon per ExplorerNode.kind — sourced from the
same glyphs CanvasToolbar already uses for each tool (see
src/layouts/panels/toolbar.py:TOOL_ICON_BY_NAME), so an element's default
icon in the Explorer always matches its toolbar tool. Kinds with no
dedicated toolbar tool (river/road/effect, picked from the Brush asset
panel rather than their own button) keep their own literal glyph."""

from __future__ import annotations

from src.layouts.panels.toolbar import TOOL_ICON_BY_NAME

DEFAULT_ICON_BY_KIND: dict[str, str] = {
    "terrain": TOOL_ICON_BY_NAME["Terreno"],
    "region": TOOL_ICON_BY_NAME["Região"],
    "asset": TOOL_ICON_BY_NAME["Plano de Fundo"],
    "npc": TOOL_ICON_BY_NAME["Spawn"],
    "mob": TOOL_ICON_BY_NAME["Spawn"],
    "text": TOOL_ICON_BY_NAME["Texto"],
    "light": TOOL_ICON_BY_NAME["Iluminação"],
    "marker": TOOL_ICON_BY_NAME["Marcador"],
    "river": "🌊",
    "road": "🛤",
    "effect": "✨",
}
