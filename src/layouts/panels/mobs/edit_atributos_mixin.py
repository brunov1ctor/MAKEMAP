"""AtributosSectionMixin — the Atributos section (stats / classification /
resistances / combate columns). Mixed into MobEditPanel (see
mob_edit_panel.py) — operates on self.* attributes MobEditPanel owns; not
meant to be instantiated on its own.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLineEdit, QDoubleSpinBox, QWidget

from src.layouts.panels.mobs.categories import (
    RARITY_DEFS, ELEMENT_OPTIONS, AI_TYPE_OPTIONS,
    BEHAVIOR_OPTIONS, ALIGNMENT_OPTIONS, RESISTANCE_KEYS, STATUS_OPTIONS, SIZE_OPTIONS,
)
from src.layouts.panels.mobs.edit_helpers import _combo, _spin, _dspin, _section_label, _field_row, _hr


class AtributosSectionMixin:
    """Atributos — three side-by-side vertical lists (general stats /
    classification / resistances), each row "label beside field" —
    matches the reference image's Atributos layout instead of the
    previous packed label-over-value grid. Combate (Crítico, Facção)
    stays as a couple of rows below the three columns since it isn't
    pictured in the reference. The Raridade *selector* lives here too
    (Visão Geral only shows the read-only badge it drives)."""

    def _build_atributos_section(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(8)

        self._hp_spin = _spin(1, 9_999_999, 100)
        self._mana_spin = _spin(0, 999999, 50)
        self._damage_spin = _spin(0, 999999, 10)
        self._defense_spin = _spin(0, 999999, 5)
        self._speed_spin = _dspin(0, 2000, 100, " u/s")
        self._precision_spin = _dspin(0, 100, 90, " %")
        self._dodge_spin = _dspin(0, 100, 5, " %")
        self._resist_fisica_spin = _dspin(-100, 100, 0, " %")
        self._resist_magica_spin = _dspin(-100, 100, 0, " %")
        self._weight_spin = _dspin(0, 99999, 0, " kg")
        self._xp_spin = _spin(0, 9_999_999, 0)
        self._gold_spin = _spin(0, 9_999_999, 0)
        self._size_combo = _combo(SIZE_OPTIONS)
        self._ai_combo = _combo(AI_TYPE_OPTIONS)
        self._behavior_combo = _combo(BEHAVIOR_OPTIONS)
        self._alignment_combo = _combo(ALIGNMENT_OPTIONS)
        self._element_combo = _combo(ELEMENT_OPTIONS)
        self._status_combo = _combo(STATUS_OPTIONS)
        self._rarity_combo = _combo([label for _k, _c, label in RARITY_DEFS])
        self._rarity_combo.currentIndexChanged.connect(self._refresh_rarity_badge)

        for spin_w in (self._hp_spin, self._mana_spin, self._damage_spin, self._defense_spin,
                       self._speed_spin, self._precision_spin, self._dodge_spin,
                       self._resist_fisica_spin, self._resist_magica_spin,
                       self._weight_spin, self._xp_spin, self._gold_spin):
            spin_w.setMaximumWidth(60)
        for w2 in (self._precision_spin, self._dodge_spin, self._resist_fisica_spin, self._resist_magica_spin):
            w2.setDecimals(1)
        for combo_w in (self._size_combo, self._ai_combo, self._behavior_combo,
                        self._alignment_combo, self._element_combo, self._status_combo,
                        self._rarity_combo):
            combo_w.setMaximumWidth(96)

        col1 = QVBoxLayout()
        col1.setSpacing(3)
        col1.addWidget(_section_label("ATRIBUTOS"))
        col1.addWidget(_hr())
        for label, widget in [
            ("HP Máximo", self._hp_spin), ("Mana Máximo", self._mana_spin),
            ("Ataque", self._damage_spin), ("Defesa", self._defense_spin),
            ("Velocidade", self._speed_spin), ("Precisão", self._precision_spin),
            ("Esquiva", self._dodge_spin), ("Resist. Física", self._resist_fisica_spin),
            ("Resist. Mágica", self._resist_magica_spin),
        ]:
            col1.addLayout(_field_row(label, widget))
        col1.addStretch()

        col2 = QVBoxLayout()
        col2.setSpacing(3)
        col2.addWidget(_section_label("CLASSIFICAÇÃO"))
        col2.addWidget(_hr())
        for label, widget in [
            ("Elemento Primário", self._element_combo), ("Tamanho", self._size_combo),
            ("XP Concedida", self._xp_spin), ("Ouro Base", self._gold_spin),
            ("Peso", self._weight_spin), ("Tipo de IA", self._ai_combo),
            ("Comportamento", self._behavior_combo), ("Alinhamento", self._alignment_combo),
            ("Raridade", self._rarity_combo), ("Status", self._status_combo),
        ]:
            col2.addLayout(_field_row(label, widget))
        col2.addStretch()

        col3 = QVBoxLayout()
        col3.setSpacing(3)
        col3.addWidget(_section_label("RESISTÊNCIAS"))
        col3.addWidget(_hr())
        self._resistance_spins: dict[str, QDoubleSpinBox] = {}
        for key, label in RESISTANCE_KEYS:
            spin = _dspin(-100, 100, 0, " %")
            spin.setDecimals(0)
            spin.setMaximumWidth(56)
            self._resistance_spins[key] = spin
            col3.addLayout(_field_row(label, spin))
        col3.addStretch()

        columns_row = QHBoxLayout()
        columns_row.setSpacing(10)
        columns_row.addLayout(col1, 1)
        columns_row.addLayout(col2, 1)
        columns_row.addLayout(col3, 1)
        outer.addLayout(columns_row)

        outer.addWidget(_section_label("COMBATE"))
        outer.addWidget(_hr())
        self._crit_spin = _dspin(0, 100, 5, " %")
        self._faction_edit = QLineEdit()
        self._faction_edit.setPlaceholderText("Ex: Bandidos, Guarda Real...")
        outer.addLayout(_field_row("Crítico", self._crit_spin))
        outer.addLayout(_field_row("Facção", self._faction_edit))

        outer.addStretch()
        return w
