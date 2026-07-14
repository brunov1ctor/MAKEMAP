"""Canvas overlays — HUD, compass, minimap, zoom control."""

from src.canvas.overlays.hud import HUDOverlay
from src.canvas.overlays.compass import Compass
from src.canvas.overlays.minimap import MiniMap
from src.canvas.overlays.zoom_control import ZoomControl

__all__ = ["HUDOverlay", "Compass", "MiniMap", "ZoomControl"]
