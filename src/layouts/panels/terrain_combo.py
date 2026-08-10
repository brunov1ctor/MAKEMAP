"""TerrainCombo — label informativo "Terreno: <nome>" reutilizável.

Mostra em qual terreno o objeto será colocado. Somente leitura —
para trocar de terreno o usuário clica no card no painel Terreno.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Signal

from src.styles.tokens import Colors


class TerrainCombo(QWidget):
    """Linha compacta '🗺 Terreno: <nome>' — somente leitura."""

    # Mantido para compatibilidade com mediators que conectam este sinal,
    # mas nunca é emitido (label não tem interação).
    terrain_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._terrain_id = ""
        self._names: dict[str, str] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        icon = QLabel("🗺")
        icon.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        row.addWidget(icon)

        self._label = QLabel("Terreno: Mapa Infinito")
        self._label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px; "
            f"background: transparent; border: none;"
        )
        row.addWidget(self._label, 1)

    def set_options(self, options: list[tuple[str, str]]):
        """Atualiza o mapa id→nome e refresca o label."""
        self._names = {tid: name for tid, name in options}
        self._refresh()

    def set_terrain(self, terrain_id: str):
        """Sincroniza o terreno ativo (chamado por TerrainMediator)."""
        self._terrain_id = terrain_id
        self._refresh()

    def _refresh(self):
        name = self._names.get(self._terrain_id, "Mapa Infinito") if self._terrain_id else "Mapa Infinito"
        self._label.setText(f"Terreno: {name}")
