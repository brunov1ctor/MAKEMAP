"""Região tool defaults.

Unlike Bioma (which scatters procedural objects via MapGenerator), a região
is just a flat translucent color painted over a user-drawn/brush-painted
area. "Tipo" is a free-text field the user fills in themselves (not a fixed
category), so there's no ZONE_TYPES enum to pick from anymore — just a
default color for a brand-new região before its own color picker is used.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

DEFAULT_ZONE_COLOR = QColor(120, 200, 120, 90)
