"""ExplorerNode — the tree model behind the Explorer panel.

Deliberately NOT the ExplorerEngine/TreeNode CRUD model in
src/engines/explorer_inspector.py: that one is built for a tree the user
edits node-by-node. This tree is the opposite — fully derived from the
canvas/mediators' own state and thrown away/rebuilt from scratch on every
sync (see ExplorerSyncMediator), so a plain, disposable dataclass is enough;
no add/remove/move API is needed."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtGui import QPixmap


@dataclass
class ExplorerNode:
    id: str
    kind: str  # "category" | "terrain" | "region" | "asset" | "effect" | "npc" | "mob" | "text" | "light" | "marker"
    label: str
    thumbnail: QPixmap | None = None
    icon_glyph: str = ""  # fallback glyph shown when there's no thumbnail
    children: list["ExplorerNode"] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)  # scene_pos etc. for "Localizar" on click
    selected: bool = False  # True when the corresponding canvas item is currently selected
    label_color: str | None = None  # user override from the icon-click popup, or None for the default
    override_key: str | None = None  # stable key into explorer_overrides; None while not yet persistable
    default_icon: str | None = None  # icon_glyph BEFORE any override — lets the edit popup offer "back to default"
