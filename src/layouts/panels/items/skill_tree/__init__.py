"""ÁRVORE DE HABILIDADES package — see canvas.py's module docstring for the
full design notes and this package's module layout (items/view/stats/
tab_creator/canvas). SkillTreeCanvas is the only symbol other panels
should import from here (see panel.py)."""

from .canvas import SkillTreeCanvas

__all__ = ["SkillTreeCanvas"]
