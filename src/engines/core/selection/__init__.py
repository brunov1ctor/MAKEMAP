"""Selection — engine.py is a pure state manager (set/add/remove/toggle/
clear over Qt's own scene.selectedItems()); queries.py holds the stateless
geometry/set logic (box, lasso, select-all, invert) that finds candidate
items without ever mutating selection itself."""

from __future__ import annotations

from . import queries
from .engine import SelectionEngine

__all__ = ["SelectionEngine", "queries"]
