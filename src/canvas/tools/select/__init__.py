"""Selection tool — modularized: tool.py dispatches mouse events to
box_select.py (default drag) or lasso_select.py (Alt+drag)."""

from __future__ import annotations

from .tool import SelectTool

__all__ = ["SelectTool"]
