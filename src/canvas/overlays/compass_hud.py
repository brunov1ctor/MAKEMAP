"""CompassHUD — info card shown next to the compass while it's expanded:
active terrain, map area (meters), and the view center's lat/lon (see
geo_format.py). Purely a readout — no interaction.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.styles.tokens import Colors
from src.canvas.overlays.scale_bar import format_distance
from src.canvas.overlays.geo_format import to_lat_lon, format_lat_lon


class CompassHUD(QFrame):
    """Small glass info card — title + separator, then one icon-badge row
    per stat (same "icon in a rounded chip, caption above, bold value
    below" language as the stat chips elsewhere in the app)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(f"""
            QFrame {{
                background: {Colors.GLASS_BG_STRONG};
                border: 1px solid {Colors.GLASS_BORDER};
                border-radius: 10px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title = QLabel("🧭 NAVEGAÇÃO")
        title.setStyleSheet(f"""
            color: {Colors.ACCENT}; font-size: 9pt; font-weight: bold;
            background: transparent; border: none;
        """)
        lay.addWidget(title)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.GLASS_BORDER}; border: none;")
        lay.addWidget(sep)

        self._terrain_lbl = self._build_row(lay, "🗺", "TERRENO")
        self._area_lbl = self._build_row(lay, "📐", "ÁREA")
        self._latlon_lbl = self._build_row(lay, "🧭", "POSIÇÃO")

        self.adjustSize()
        self.hide()

    def _build_row(self, lay: QVBoxLayout, icon: str, caption: str) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedSize(24, 24)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            background: {Colors.ACCENT_DIM}; border-radius: 7px; font-size: 11px;
        """)
        row.addWidget(icon_lbl)

        col = QVBoxLayout()
        col.setSpacing(0)
        cap_lbl = QLabel(caption)
        cap_lbl.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 7pt; font-weight: bold;
            background: transparent; border: none;
        """)
        col.addWidget(cap_lbl)

        value_lbl = QLabel("—")
        value_lbl.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold;
            background: transparent; border: none;
        """)
        col.addWidget(value_lbl)
        row.addLayout(col, 1)

        lay.addLayout(row)
        return value_lbl

    def update_info(self, terrain_name: str, map_width_m: float, map_height_m: float,
                     center_x_m: float, center_y_m: float):
        self._terrain_lbl.setText(terrain_name or "Nenhum terreno ativo")
        self._area_lbl.setText(f"{format_distance(map_width_m)} × {format_distance(map_height_m)}")
        lat, lon = to_lat_lon(center_x_m, center_y_m)
        self._latlon_lbl.setText(format_lat_lon(lat, lon))
        # setText() alone leaves the layout's cached size hint stale, so a
        # bare adjustSize() right after can undersize the frame (and then
        # every row gets clipped to that stale, narrower column width) —
        # force a fresh size hint before resizing, then re-activate so
        # children actually get laid out into the new, bigger rect (a lone
        # adjustSize() grows the frame but doesn't reposition its children).
        self.layout().invalidate()
        self.layout().activate()
        self.adjustSize()
        self.layout().invalidate()
        self.layout().activate()
