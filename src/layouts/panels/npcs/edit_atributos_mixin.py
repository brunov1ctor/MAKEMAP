"""AtributosSectionMixin — repurposed from the Mob template as "🎭
Comportamento": how this NPC reacts to and survives combat (initial state,
player reaction, can-be-attacked/flees/dies/respawns, respawn timing, spawn
radius, shadow %). Mixed into NPCEditPanel (see npc_edit_panel.py) —
operates on self.* attributes NPCEditPanel owns; not meant to be
instantiated on its own.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget

from src.layouts.panels.mobs.edit_helpers import _combo, _spin, _dspin, _checkbox, _section_label, _field_row, _hr

INITIAL_STATE_OPTIONS = ["Neutro", "Hostil", "Amigável"]
PLAYER_REACTION_OPTIONS = ["Neutro", "Hostil", "Amigável"]


class AtributosSectionMixin:
    """Comportamento — estado inicial/reação ao jogador side by side, then a
    row of behavior checkboxes, then respawn/spawn-radius/shadow tuning."""

    def _build_atributos_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(8)

        outer.addWidget(_section_label("REAÇÃO"))
        outer.addWidget(_hr())
        self._initial_state_combo = _combo(INITIAL_STATE_OPTIONS)
        self._player_reaction_combo = _combo(PLAYER_REACTION_OPTIONS)
        reaction_row = QHBoxLayout()
        reaction_row.setSpacing(10)
        reaction_row.addLayout(_field_row("Estado inicial", self._initial_state_combo))
        reaction_row.addLayout(_field_row("Reação ao jogador", self._player_reaction_combo))
        outer.addLayout(reaction_row)

        outer.addWidget(_section_label("COMBATE"))
        outer.addWidget(_hr())
        self._can_be_attacked_check = _checkbox("Pode ser atacado")
        self._flees_when_attacked_check = _checkbox("Foge ao ser atacado")
        self._can_die_check = _checkbox("Morre")
        self._can_respawn_check = _checkbox("Renasce")
        checks_row1 = QHBoxLayout()
        checks_row1.setSpacing(14)
        checks_row1.addWidget(self._can_be_attacked_check)
        checks_row1.addWidget(self._flees_when_attacked_check)
        outer.addLayout(checks_row1)
        checks_row2 = QHBoxLayout()
        checks_row2.setSpacing(14)
        checks_row2.addWidget(self._can_die_check)
        checks_row2.addWidget(self._can_respawn_check)
        outer.addLayout(checks_row2)

        outer.addWidget(_section_label("RESPAWN / ÁREA"))
        outer.addWidget(_hr())
        self._respawn_time_spin = _spin(0, 999999, 0)
        self._respawn_time_spin.setSuffix(" min")
        self._spawn_radius_spin = _dspin(0, 99999, 0, " %")
        self._shadow_pct_spin = _dspin(0, 100, 0, " %")
        respawn_row = QHBoxLayout()
        respawn_row.setSpacing(10)
        respawn_row.addLayout(_field_row("Tempo para renascer", self._respawn_time_spin))
        respawn_row.addLayout(_field_row("Raio %", self._spawn_radius_spin))
        respawn_row.addLayout(_field_row("Sombrio %", self._shadow_pct_spin))
        outer.addLayout(respawn_row)

        # Same role as Mobs' Altura field (edit_atributos_mixin.py) — scales
        # how far a stamped npc's shadow reaches (see occluder_rects() in
        # lighting_compositor.py); 0 (the default) casts none at all.
        self._height_spin = _dspin(0, 999, 0, " m")
        outer.addLayout(_field_row("Altura", self._height_spin))

        outer.addStretch()
        return w
