"""RegionModeButton — consolidates Região/Estrada/Rio/Bioma into one toolbar slot.

All four draw a polygon or path on the canvas via the same click-to-add-point
flow (see RegionTool/RoadTool/RiverTool in brush_tool.py); Bioma specifically
draws a region (RegionTool) and additionally tags it with a generation preset
(Forest/Mountain/Village/Desert — see engines/map/presets.py) so the finished
polygon gets populated with that biome's objects instead of the plain default.
"""

from __future__ import annotations

from PySide6.QtWidgets import QToolButton, QMenu
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.engines.map.presets import PRESETS

# key -> (icon, display label) for the Bioma submenu
_BIOME_PRESETS = [
    ("forest", "🌲", "Floresta"),
    ("mountain", "🏔", "Montanhas"),
    ("village", "🏰", "Vila"),
    ("desert", "🏜", "Deserto"),
]

_MODE_ICON = {"Região": "▭", "Estrada": "⟋", "Rio": "〰", "Bioma": "◐"}


class RegionModeButton(QToolButton):
    """Dropdown that activates Região/Estrada/Rio, or Região with a biome preset."""

    # Canvas tool name to activate — "Região", "Estrada", or "Rio".
    mode_activated = Signal(str)
    # Biome preset key (from PRESETS), or "" to clear a previously-picked one.
    preset_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText(_MODE_ICON["Região"])
        self.setToolTip("Região")
        self.setFixedSize(32, 32)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 6px;
                font-size: 14px; color: {Colors.TEXT_SECONDARY};
                background: transparent;
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY};
            }}
            QToolButton:checked {{
                background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
            QToolButton::menu-indicator {{ image: none; }}
        """)

        menu_style = f"""
            QMenu {{
                background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER}; padding: 4px;
            }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """

        menu = QMenu(self)
        menu.setStyleSheet(menu_style)

        act_region = menu.addAction(f"{_MODE_ICON['Região']} Região")
        act_region.triggered.connect(lambda: self._pick("Região"))

        act_road = menu.addAction(f"{_MODE_ICON['Estrada']} Estrada")
        act_road.triggered.connect(lambda: self._pick("Estrada"))

        act_river = menu.addAction(f"{_MODE_ICON['Rio']} Rio")
        act_river.triggered.connect(lambda: self._pick("Rio"))

        biome_menu = menu.addMenu(f"{_MODE_ICON['Bioma']} Bioma")
        biome_menu.setStyleSheet(menu_style)
        for key, icon, label in _BIOME_PRESETS:
            if key not in PRESETS:
                continue
            act = biome_menu.addAction(f"{icon} {label}")
            act.triggered.connect(lambda checked=False, k=key: self._pick_biome(k))

        self.setMenu(menu)

    def _pick(self, name: str):
        self.setText(_MODE_ICON[name])
        self.setToolTip(name)
        self.preset_selected.emit("")  # explicit non-biome pick clears any preset
        self.mode_activated.emit(name)

    def _pick_biome(self, preset_key: str):
        preset = PRESETS.get(preset_key)
        self.setText(_MODE_ICON["Bioma"])
        self.setToolTip(f"Bioma: {preset.name}" if preset else "Bioma")
        self.preset_selected.emit(preset_key)
        self.mode_activated.emit("Região")
