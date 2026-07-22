"""Pure widget-builder helpers shared across MobEditPanel's 3 sections —
no `self`/panel state, just plain functions taking values and returning a
widget or layout. Split out of mob_edit_panel.py to keep that file focused
on MobEditPanel itself.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QDoubleSpinBox, QPushButton, QWidget, QAbstractSpinBox,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_label, item_rarity_color

_INPUT_STYLE = f"""
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
        border-radius: 5px; padding: 1px 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px;
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {Colors.ACCENT};
    }}
    QComboBox QAbstractItemView {{
        background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY};
        selection-background-color: {Colors.ACCENT_DIM}; border: 1px solid {Colors.BORDER};
    }}
    QComboBox::drop-down {{ width: 12px; border: none; }}
    QLabel {{ color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none; }}
"""


def _combo(options: list[str], current: str = "") -> QComboBox:
    c = QComboBox()
    c.addItems(options)
    if current and current in options:
        c.setCurrentText(current)
    return c


def _spin(minimum=0, maximum=999999, value=0) -> QSpinBox:
    s = QSpinBox()
    s.setRange(minimum, maximum)
    s.setValue(value)
    # Up/down buttons dropped entirely (not just hidden via QSS — a
    # stylesheet width:0 on the button still leaves the arrow glyph
    # painted, overlapping the value text) so the full number is legible
    # in the narrow columns this panel now uses.
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return s


def _dspin(minimum=0.0, maximum=100.0, value=0.0, suffix="") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setValue(value)
    s.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    if suffix:
        s.setSuffix(suffix)
    return s


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
    return lbl


def _field_row(label_text: str, widget: QWidget) -> QHBoxLayout:
    """Label beside its field (not stacked above it) — matches the
    reference design for Visão Geral and Atributos alike. The label gets
    an explicit border:none/background:transparent of its own (on top of
    the panel-wide _INPUT_STYLE rule) since a QLabel sitting directly
    next to a bordered QComboBox/QSpinBox is exactly the spot a stray box
    around the label would be most noticeable."""
    row = QHBoxLayout()
    row.setSpacing(6)
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
    # The stretch belongs on the field, not the label — a stretched label
    # keeps its text left-aligned but grows to fill the row, which reads
    # as a big gap between the label and its field. Atributos' columns
    # are narrow enough (label+field already exceed the column width)
    # that this never showed there; Visão Geral's wider rows made it
    # obvious.
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


def _stat_field(label_text: str, widget: QWidget) -> QVBoxLayout:
    """Label above value, no border — for the "Informações Gerais" card
    (see _build_overview_section), which supplies the actual borderless/
    bold QSS for these value widgets via its own stylesheet cascading
    down to them, so this helper only handles the label+layout part."""
    col = QVBoxLayout()
    col.setSpacing(2)
    caption = QLabel(label_text)
    caption.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
    col.addWidget(caption)
    col.addWidget(widget)
    return col


def _vdivider() -> QFrame:
    line = QFrame()
    line.setFixedWidth(1)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
    return line


def _stat_row(fields: list[tuple[str, QWidget]]) -> QHBoxLayout:
    """A row of _stat_field columns separated by thin vertical dividers —
    the Nível/Tipo/Tier and Categoria/Subcategoria rows in the
    Informações Gerais card."""
    row = QHBoxLayout()
    row.setSpacing(14)
    for i, (label_text, widget) in enumerate(fields):
        if i > 0:
            row.addWidget(_vdivider())
        row.addLayout(_stat_field(label_text, widget), 1)
    return row


def _no_wheel(widget):
    """Ignores mouse-wheel events on `widget` instead of letting it bump
    the current value — the panel packs dozens of spin/combo boxes into a
    scrollable column (see _CollapsibleSection), so scrolling past one
    used to silently change whatever field the cursor happened to be
    over. Overriding the instance's own wheelEvent (rather than an
    installed event filter) keeps Qt's normal ignored-event propagation:
    the scroll area underneath still receives the wheel event and scrolls
    normally, exactly as if the cursor were over any plain label."""
    widget.wheelEvent = lambda event: event.ignore()
    return widget


def _hr() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {Colors.BORDER_SUBTLE}; border: none;")
    return line


def _extra_header_row(title: str, button_text: str, on_click) -> QHBoxLayout:
    """A DROPS/HABILIDADES/ASSETS sub-header inside Informações Extras —
    small-caps label on the left, an optional "+ Novo X" link on the
    right (same transparent/ACCENT link style as "+ Nova categoria" in
    the sidebar). `button_text` empty skips the button entirely (Drops
    has no header-row add button — see its own inline add row instead)."""
    row = QHBoxLayout()
    row.addWidget(_section_label(title))
    row.addStretch()
    if button_text:
        btn = QPushButton(button_text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {Colors.ACCENT}; border: none; font-size: 9px; font-weight: bold; padding: 0; }}
            QPushButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        btn.clicked.connect(on_click)
        row.addWidget(btn)
    return row


def _rarity_chip_label(rarity_key: str) -> QLabel:
    chip = QLabel(item_rarity_label(rarity_key))
    color = item_rarity_color(rarity_key)
    chip.setStyleSheet(
        f"font-size: 9px; font-weight: bold; border-radius: 6px; padding: 2px 8px; "
        f"background: {color}33; color: {color};"
    )
    return chip
