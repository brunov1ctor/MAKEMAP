"""CategoryEditPanel — full create/edit panel for a single mob_categories
folder. Replaces the old single inline text field ("+ Nova categoria" in
panel_category_mixin.py, icon always hardcoded to '🐾') with a real form:
name, an icon grid, a card border color, an uploaded image, and a separate
border color around that image.

Mirrors RegionEditPanel's shell (glass paintEvent, CollapsibleSection
groups) and lives as page 1 of MobsPanel's left-column QStackedWidget
(see panel_category_mixin.py's _build_left_column/self._left_stack) —
swapped in over the CATEGORIAS sidebar itself, not the right-hand
MobEditPanel slot (a category isn't a mob) and not a separate dialog/
window. Every confirmation (missing name, delete) stays inline in this
panel too — no native QMessageBox popups, which read as a window outside
the app.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSizePolicy,
    QToolButton, QLineEdit, QScrollArea, QWidget, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen, QBrush, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.collapsible_section import CollapsibleSection
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider
from src.layouts.panels.mobs.edit_widgets import _DropImageButton

# Curated set for the icon grid — the old fixed CATEGORY_DEFS icons
# (categories.py, now just seed data) plus a much wider spread of
# creature/monster/gear/element glyphs, so most category concepts have a
# real pick instead of needing the free-text fallback. The grid scrolls
# (see _IconPicker) specifically so this list can stay long without
# blowing up the panel's height.
ICON_CHOICES = [
    "☠", "🐺", "🧟", "🤖", "🧑‍🤝‍🧑", "🐉", "🐛", "🐊", "🔥", "🌿", "👹", "❔",
    "🐾", "💎", "💠", "👑", "📁", "📦", "🗡", "🛡", "🏹", "🔮", "⚔", "🦴",
    "🐍", "🦂", "🕷", "🦇", "🦉", "🐗", "🐻", "🐆", "🦁", "🐯", "🐘", "🦍",
    "🦅", "🦖", "🦕", "🐙", "🦑", "🐢", "🐬", "🐳", "🦈", "🐌", "🐝", "🦋",
    "👻", "💀", "🧛", "🧙", "🧌", "🧝", "🧚", "🧞", "🧜", "👽", "👾", "🎃",
    "⚡", "❄", "🌊", "🌪", "🌋", "☄", "🌙", "⭐", "✨", "💥", "🌫", "🍄",
    "🗿", "⚱", "🏺", "🔱", "🪓", "🔪", "💣", "🪃", "🧿", "🕸",
    "🐴", "🦄", "🐐", "🐑", "🐄", "🐷", "🐔", "🦃", "🦢", "🦆", "🦜", "🐇",
]


class _ColorSwatch(QWidget):
    """Compact color preview + clear button — no picker of its own. All 3
    of these (card border, image border, tag text) sit side by side in one
    row, hence the short 1-word labels; clicking any opens the single
    shared _SharedColorPicker below them (see CategoryEditPanel.
    _activate_color_target) instead of each swatch carrying an independent
    ~150-line Hue/SV/RGB/hex picker. Has a real "no color chosen" state —
    an empty category field means "fall back to the old hardcoded
    category_badge_color", not "black"."""

    clicked = Signal()
    cleared = Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._color = QColor("#4FC3F7")
        self._has_color = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(lbl)

        self._swatch_btn = QToolButton()
        self._swatch_btn.setFixedHeight(24)
        self._swatch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch_btn.clicked.connect(self.clicked.emit)

        self._clear_btn = QToolButton()
        self._clear_btn.setText("✕")
        self._clear_btn.setToolTip("Usar cor padrão")
        self._clear_btn.setFixedSize(20, 20)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 10px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}
        """)
        self._clear_btn.clicked.connect(self._on_clear)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._swatch_btn, 1)
        row.addWidget(self._clear_btn)
        outer.addLayout(row)

        self._refresh_swatch()

    def _on_clear(self):
        self._has_color = False
        self._refresh_swatch()
        self.cleared.emit()

    def _refresh_swatch(self):
        if self._has_color:
            self._swatch_btn.setStyleSheet(f"""
                QToolButton {{ background: {self._color.name()}; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
                QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
            """)
        else:
            self._swatch_btn.setStyleSheet(f"""
                QToolButton {{ background: rgba(255,255,255,0.04); border: 1px dashed {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
                QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
            """)

    # ─── Public API ───

    def set_color(self, hex_color: str):
        if not hex_color:
            self._has_color = False
        else:
            self._color = QColor(hex_color)
            self._has_color = True
        self._refresh_swatch()

    def color(self) -> str:
        return self._color.name() if self._has_color else ""


class _SharedColorPicker(QFrame):
    """The Hue/SV/RGB/hex picker itself — same widgets/logic as
    RegionEditPanel._build_color_picker, but with no swatch of its own.
    CategoryEditPanel shows/hides this single instance under whichever
    _ColorSwatch was last clicked instead of giving each swatch its own
    copy (the "2 previews using the same picker" simplification)."""

    color_changed = Signal(str)  # hex, always non-empty

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._color = QColor("#4FC3F7")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)

        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(16)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        lay.addWidget(self._hue_bar)

        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(90)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        lay.addWidget(self._sv_square)

        self._r_slider = ColorSlider("R", 0, 255, self._color.red())
        self._g_slider = ColorSlider("G", 0, 255, self._color.green())
        self._b_slider = ColorSlider("B", 0, 255, self._color.blue())
        for slider in (self._r_slider, self._g_slider, self._b_slider):
            slider.value_changed.connect(self._on_rgb_slider_changed)
        lay.addWidget(self._r_slider)
        lay.addWidget(self._g_slider)
        lay.addWidget(self._b_slider)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hex_label = QLabel("#")
        hex_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hex_label)
        self._hex_input = QLineEdit()
        self._hex_input.setFixedHeight(22)
        self._hex_input.setMaxLength(6)
        self._hex_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10px; padding: 0 4px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._hex_input.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self._hex_input, 1)
        lay.addLayout(hex_row)

        h, s, v, _a = self._color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._sync_all(emit=False)

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1], self._hsv[2] = s, v
        self._apply_hsv()

    def _apply_hsv(self):
        h, s, v = self._hsv
        self._set_color(QColor.fromHsv(h, round(s * 255 / 100), round(v * 255 / 100)), sync_hsv=False)

    def _on_rgb_slider_changed(self, _value: int):
        color = QColor(self._r_slider.value(), self._g_slider.value(), self._b_slider.value())
        self._set_color(color, sync_rgb=False)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) != 6:
            return
        try:
            r, g, b = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            return
        self._set_color(QColor(r, g, b), sync_hex=False)

    def _set_color(self, color: QColor, sync_hsv: bool = True, sync_rgb: bool = True, sync_hex: bool = True):
        self._color = QColor(color)
        if sync_hsv:
            h, s, v, _a = self._color.getHsv()
            self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._sync_all(emit=True, sync_hsv=sync_hsv, sync_rgb=sync_rgb, sync_hex=sync_hex)

    def _sync_all(self, emit: bool, sync_hsv: bool = True, sync_rgb: bool = True, sync_hex: bool = True):
        if sync_hsv:
            self._hue_bar.set_hue(self._hsv[0])
            self._sv_square.set_hue(self._hsv[0])
            self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        if sync_rgb:
            for slider, value in ((self._r_slider, self._color.red()), (self._g_slider, self._color.green()),
                                   (self._b_slider, self._color.blue())):
                slider.blockSignals(True)
                slider.set_value(value)
                slider.blockSignals(False)
        if sync_hex:
            self._hex_input.blockSignals(True)
            self._hex_input.setText(self._color.name(QColor.NameFormat.HexRgb).lstrip("#").upper())
            self._hex_input.blockSignals(False)
        if emit:
            self.color_changed.emit(self._color.name())

    # ─── Public API ───

    def set_color(self, hex_color: str):
        """Loads a color WITHOUT emitting color_changed — used when
        switching which swatch this shared picker is currently editing."""
        self._color = QColor(hex_color) if hex_color else QColor("#4FC3F7")
        h, s, v, _a = self._color.getHsv()
        self._hsv = [max(0, h), s * 100 // 255, v * 100 // 255]
        self._sync_all(emit=False)


class _IconPicker(QWidget):
    """Current-icon preview button that toggles an inline grid of curated
    emoji choices below it, plus a free-text field for anything not in the
    grid — categories could only ever get an icon by free-typing before
    this panel existed (or the DB default '🐾'), so a custom entry stays
    possible alongside the grid."""

    icon_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon = "🐾"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._preview_btn = QToolButton()
        self._preview_btn.setFixedSize(32, 32)
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_btn.setStyleSheet(f"""
            QToolButton {{ font-size: 16px; background: rgba(255,255,255,0.06);
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)
        self._preview_btn.clicked.connect(self._toggle_grid)
        row.addWidget(self._preview_btn)

        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("Ou digite um emoji...")
        self._custom_edit.setMaxLength(8)
        self._custom_edit.setStyleSheet(f"""
            QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 4px 6px; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._custom_edit.editingFinished.connect(self._on_custom_entered)
        row.addWidget(self._custom_edit, 1)
        outer.addLayout(row)

        # ICON_CHOICES is long enough now (80+) that laid out flat it would
        # blow past the panel's own height — a fixed-height QScrollArea
        # keeps the grid itself scrollable instead of growing the whole
        # panel every time an entry gets added to the list.
        self._grid_frame = QFrame()
        grid = QGridLayout(self._grid_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        cols = 6
        for i, choice in enumerate(ICON_CHOICES):
            btn = QToolButton()
            btn.setText(choice)
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{ font-size: 14px; background: rgba(255,255,255,0.04);
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; }}
                QToolButton:hover {{ border-color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            """)
            btn.clicked.connect(lambda _c=False, ic=choice: self._pick(ic))
            grid.addWidget(btn, i // cols, i % cols)

        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setFixedHeight(150)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
        )
        self._grid_scroll.setWidget(self._grid_frame)
        self._grid_scroll.hide()
        outer.addWidget(self._grid_scroll)

        self._refresh_preview()

    def _toggle_grid(self):
        self._grid_scroll.setVisible(not self._grid_scroll.isVisible())

    def _pick(self, icon: str):
        self._icon = icon
        self._refresh_preview()
        self._custom_edit.blockSignals(True)
        self._custom_edit.clear()
        self._custom_edit.blockSignals(False)
        self.icon_changed.emit(icon)

    def _on_custom_entered(self):
        text = self._custom_edit.text().strip()
        if text:
            self._icon = text
            self._refresh_preview()
            self.icon_changed.emit(text)

    def _refresh_preview(self):
        self._preview_btn.setText(self._icon)

    def set_icon(self, icon: str):
        self._icon = icon or "🐾"
        self._refresh_preview()

    def icon(self) -> str:
        return self._icon


class CategoryEditPanel(QFrame):
    """Create/edit panel for one mob_categories folder — the Mobs panel's
    right-column 3rd page. `load(None, parent_id)` opens in create mode
    inside `parent_id`; `load(category_dict, parent_id)` pre-fills every
    field for editing that category in place."""

    PANEL_WIDTH = 300

    # {id (None if creating), parent_id, name, icon, border_color,
    #  image_path, image_border_color}
    save_requested = Signal(dict)
    delete_requested = Signal(str)
    close_requested = Signal()
    content_changed = Signal()  # a section expanded/collapsed — panel needs re-sizing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._category_id: str | None = None
        self._delete_armed = False
        self._parent_id: str | None = None
        self._image_path = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
        )

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(8)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)
        icon_lbl = QLabel("📁")
        icon_lbl.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon_lbl)
        self._title_lbl = QLabel("NOVA CATEGORIA")
        self._title_lbl.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(self._title_lbl)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent; }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)
        layout.addWidget(self._sep())

        # ═══ Seção 1 — Informações ═══
        info_section = CollapsibleSection("Informações", expanded=True)
        info_section.content_changed.connect(self.content_changed.emit)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nome da categoria...")
        self._name_edit.setStyleSheet(self._input_style())
        self._name_edit.textEdited.connect(lambda _t: self._set_name_error(""))
        info_section.content_layout.addWidget(self._field_row("Nome", self._name_edit))

        # Inline "nome obrigatório" message — no native QMessageBox popup.
        self._name_error_lbl = QLabel("")
        self._name_error_lbl.setStyleSheet(f"color: {Colors.ERROR}; font-size: 9px; background: transparent; border: none;")
        self._name_error_lbl.hide()
        info_section.content_layout.addWidget(self._name_error_lbl)

        self._icon_picker = _IconPicker()
        info_section.content_layout.addWidget(self._field_row("Ícone", self._icon_picker))

        layout.addWidget(info_section)
        layout.addWidget(self._sep())

        # ═══ Seção 2 — Aparência ═══
        appearance_section = CollapsibleSection("Aparência", expanded=True)
        appearance_section.content_changed.connect(self.content_changed.emit)

        # All 3 swatches share ONE picker underneath (self._color_picker)
        # instead of each carrying its own full Hue/SV/RGB/hex picker (see
        # _ColorSwatch/_SharedColorPicker and _activate_color_target).
        # Short 1-word labels (Borda/Tag/Texto instead of the full "Cor da
        # borda do card" etc.) are what make 3-across fit this ~280px-wide
        # panel at all.
        self._color_target: str | None = None  # "border" | "image_border" | "tag_text" | None
        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        self._border_swatch = _ColorSwatch("Borda")
        self._border_swatch.clicked.connect(lambda: self._activate_color_target("border"))
        self._border_swatch.cleared.connect(lambda: self._on_swatch_cleared("border"))
        swatches_row.addWidget(self._border_swatch, 1)

        self._image_border_swatch = _ColorSwatch("Borda da imagem")
        self._image_border_swatch.clicked.connect(lambda: self._activate_color_target("image_border"))
        self._image_border_swatch.cleared.connect(lambda: self._on_swatch_cleared("image_border"))
        swatches_row.addWidget(self._image_border_swatch, 1)

        self._tag_text_swatch = _ColorSwatch("Texto")
        self._tag_text_swatch.clicked.connect(lambda: self._activate_color_target("tag_text"))
        self._tag_text_swatch.cleared.connect(lambda: self._on_swatch_cleared("tag_text"))
        swatches_row.addWidget(self._tag_text_swatch, 1)
        appearance_section.content_layout.addLayout(swatches_row)

        self._color_picker = _SharedColorPicker()
        self._color_picker.color_changed.connect(self._on_shared_color_changed)
        self._color_picker.hide()
        appearance_section.content_layout.addWidget(self._color_picker)

        self._image_btn = _DropImageButton()
        self._image_btn.setText("+ Imagem")
        self._image_btn.setFixedSize(80, 80)
        self._image_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._image_btn.setStyleSheet(f"""
            QToolButton {{ color: {Colors.TEXT_MUTED}; font-size: 10px; background: rgba(255,255,255,0.04);
                border: 1px dashed {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
            QToolButton:hover {{ border-color: {Colors.ACCENT}; }}
        """)
        self._image_btn.clicked.connect(self._on_pick_image)
        self._image_btn.image_dropped.connect(self._set_image_path)
        appearance_section.content_layout.addWidget(self._field_row("Imagem (clique ou arraste)", self._image_btn))

        layout.addWidget(appearance_section)
        layout.addWidget(self._sep())

        # ═══ Ações ═══
        self._save_btn = QToolButton()
        self._save_btn.setText("✓ Salvar Categoria")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setMinimumHeight(34)
        self._save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._save_btn.setStyleSheet(f"""
            QToolButton {{
                background: {Colors.SUCCESS}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold;
            }}
            QToolButton:hover {{ background: #7bc97e; }}
        """)
        self._save_btn.clicked.connect(self._on_save_clicked)
        layout.addWidget(self._save_btn)

        self._DELETE_BTN_DEFAULT_STYLE = f"""
            QToolButton {{ background: transparent; border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;
                color: {Colors.TEXT_MUTED}; font-size: 10px; }}
            QToolButton:hover {{ border-color: {Colors.ERROR}; color: {Colors.ERROR}; }}
        """
        self._delete_btn = QToolButton()
        self._delete_btn.setText("🗑 Excluir Categoria")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setMinimumHeight(30)
        self._delete_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._delete_btn.setStyleSheet(self._DELETE_BTN_DEFAULT_STYLE)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        self._delete_btn.hide()
        layout.addWidget(self._delete_btn)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

    # ─── Helpers ───

    def _field_row(self, label: str, widget) -> QWidget:
        row = QWidget()
        lay = QVBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return row

    def _input_style(self) -> str:
        return f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 4px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """

    def _sep(self) -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _on_pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Imagem", "", "Imagens (*.png *.jpg *.jpeg *.webp)")
        if path:
            self._set_image_path(path)

    def _set_image_path(self, path: str):
        self._image_path = path
        pixmap = QPixmap(path) if path else QPixmap()
        has_image = not pixmap.isNull()
        self._image_btn.setText("" if has_image else "+ Imagem")
        self._image_btn.set_cover_pixmap(pixmap if has_image else None)

    def _set_name_error(self, message: str):
        self._name_error_lbl.setText(message)
        self._name_error_lbl.setVisible(bool(message))

    def _swatch_for_target(self, target: str) -> "_ColorSwatch":
        return {
            "border": self._border_swatch,
            "image_border": self._image_border_swatch,
            "tag_text": self._tag_text_swatch,
        }[target]

    def _activate_color_target(self, target: str):
        """Clicking a swatch loads its color into the one shared picker
        and shows it; clicking the SAME swatch again (picker already open
        on that target) just closes it instead of doing nothing."""
        if self._color_target == target and self._color_picker.isVisible():
            self._color_picker.hide()
            self._color_target = None
            self.content_changed.emit()
            return
        self._color_target = target
        self._color_picker.set_color(self._swatch_for_target(target).color())
        self._color_picker.show()
        self.content_changed.emit()

    def _on_shared_color_changed(self, hex_color: str):
        if self._color_target:
            self._swatch_for_target(self._color_target).set_color(hex_color)

    def _on_swatch_cleared(self, target: str):
        # Clearing the swatch currently being edited also closes the
        # picker — leaving it open would keep showing a color the swatch
        # no longer has.
        if target == self._color_target:
            self._color_picker.hide()
            self._color_target = None
            self.content_changed.emit()

    def _on_save_clicked(self):
        name = self._name_edit.text().strip()
        if not name:
            self._set_name_error("Digite um nome para a categoria.")
            self._name_edit.setFocus()
            return
        self._set_name_error("")
        self.save_requested.emit({
            "id": self._category_id,
            "parent_id": self._parent_id,
            "name": name,
            "icon": self._icon_picker.icon(),
            "border_color": self._border_swatch.color(),
            "image_path": self._image_path,
            "image_border_color": self._image_border_swatch.color(),
            "tag_text_color": self._tag_text_swatch.color(),
        })

    # Deleting a category needs some "are you sure" step (it cascades to
    # subfolders) but a native QMessageBox reads as a window outside the
    # app — this button arms itself in place instead: first click swaps it
    # to a red "confirmar" state, second click (within _DELETE_ARM_MS)
    # actually deletes. Any other interaction with the panel disarms it.
    _DELETE_ARM_MS = 4000

    def _on_delete_clicked(self):
        if not self._category_id:
            return
        if not self._delete_armed:
            self._arm_delete()
            return
        self._disarm_delete()
        self.delete_requested.emit(self._category_id)

    def _arm_delete(self):
        self._delete_armed = True
        self._delete_btn.setText("⚠ Confirmar exclusão?")
        self._delete_btn.setStyleSheet(f"""
            QToolButton {{ background: {Colors.ERROR}; border: 1px solid {Colors.ERROR}; border-radius: 6px;
                color: white; font-size: 10px; font-weight: bold; }}
            QToolButton:hover {{ background: #ff6b6b; }}
        """)
        QTimer.singleShot(self._DELETE_ARM_MS, self._disarm_delete_if_stale)

    def _disarm_delete_if_stale(self):
        # A real second click already disarmed+emitted in _on_delete_clicked
        # before this timeout fires — only revert if it's still armed.
        if self._delete_armed:
            self._disarm_delete()

    def _disarm_delete(self):
        self._delete_armed = False
        self._delete_btn.setText("🗑 Excluir Categoria")
        self._delete_btn.setStyleSheet(self._DELETE_BTN_DEFAULT_STYLE)

    # ─── Public API ───

    def load(self, category: dict | None, parent_id: str | None):
        self._category_id = category["id"] if category else None
        self._parent_id = parent_id
        self._title_lbl.setText("EDITAR CATEGORIA" if category else "NOVA CATEGORIA")
        self._delete_btn.setVisible(bool(category))
        self._disarm_delete()
        self._set_name_error("")

        self._name_edit.setText(category["name"] if category else "")
        self._icon_picker.set_icon((category or {}).get("icon") or "🐾")
        self._border_swatch.set_color((category or {}).get("border_color") or "")
        self._image_border_swatch.set_color((category or {}).get("image_border_color") or "")
        self._tag_text_swatch.set_color((category or {}).get("tag_text_color") or "")
        self._color_picker.hide()
        self._color_target = None
        self._set_image_path((category or {}).get("image_path") or "")

    def focus_name(self):
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.fillPath(path, QColor(11, 25, 41, 235))
        grad = QLinearGradient(0, 0, 0, h * 0.15)
        grad.setColorAt(0.0, QColor(255, 255, 255, 10))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.drawPath(path)
        p.end()
