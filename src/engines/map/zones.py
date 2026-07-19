"""Zone types — Cities Skylines-style colored area tags for the Região tool.

Unlike Bioma (which scatters procedural objects via MapGenerator), a zone is
just a flat translucent color painted over a user-drawn polygon, tagging that
area as Residencial/Comercial/etc. No automatic lot subdivision along roads —
that's a much larger simulation feature, out of scope here.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# key -> (icon, display label, fill color)
ZONE_TYPES = [
    ("residential", "🏠", "Residencial", QColor(120, 200, 120, 90)),
    ("commercial", "🏬", "Comercial", QColor(90, 160, 230, 90)),
    ("industrial", "🏭", "Industrial", QColor(230, 190, 60, 90)),
    ("institutional", "🏛", "Institucional", QColor(150, 130, 220, 90)),
]

ZONE_COLORS = {key: color for key, _icon, _label, color in ZONE_TYPES}
