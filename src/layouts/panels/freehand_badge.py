"""FreehandBadge — small pill that follows the mouse while a "Livre"
terreno boundary is being drawn, so the click-to-place-point mode reads as
clearly active no matter where on the canvas the cursor currently is.

Also doubles as the live measurement readout (distance from the last
placed point + angle), CAD-style dynamic input — see
TerrainFreehandTool.mouse_move / TerrainMediator._on_freehand_preview.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel

_INSTRUCTION_FRESH = (
    "✏ Clique para adicionar pontos (arraste o último para ajustar, "
    "botão direito curva o último segmento) — lápis de novo para finalizar, Esc cancela"
)
_INSTRUCTION_EDIT = (
    "✏ Clique numa quina existente para editar a forma, ou em qualquer lugar "
    "para desenhar do zero — Esc cancela"
)


class FreehandBadge(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._instruction = _INSTRUCTION_FRESH
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(f"""
            background: transparent;
            color: {Colors.TEXT_PRIMARY};
            font-size: 10px;
            font-weight: bold;
            padding: 6px 12px;
        """)
        self.reset()

    def reset(self, editable: bool | None = None):
        if editable is not None:
            self._instruction = _INSTRUCTION_EDIT if editable else _INSTRUCTION_FRESH
        self.setText(self._instruction)
        self.adjustSize()

    def set_measurement(self, distance_m: float | None, angle_deg: float | None):
        if distance_m is None or angle_deg is None:
            self.reset()
            return
        self.setText(f"{self._instruction}\n📏 {distance_m:.1f}m   ∠ {angle_deg:.0f}°")
        self.adjustSize()

    def paintEvent(self, event):
        paint_glass_panel(self)
        super().paintEvent(event)
