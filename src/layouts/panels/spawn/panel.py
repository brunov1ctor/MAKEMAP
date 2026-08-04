"""Spawn Panel — 'Spawn de Mobs' toolbar panel.

Categories mirror the Mobs module's live category tree (same DB rows, same
icons — see SpawnMediator._refresh_categories) — picking one opens the
adjacent SpawnMobSubPanel listing every mob tagged under it. "Modo Carimbo"
(Tamanho/Quantidade) controls the composed group-portrait stamp preview
(see portrait_compose.compose_group_portrait) shown here before it's
clicked onto the map.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton,
    QWidget, QScrollArea, QSpinBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors
from src.layouts.panel_manager import paint_glass_panel
from src.layouts.panels.brush.slider import BrushSlider

_PREVIEW_SIZE = 56


def _no_wheel(widget):
    """Stops accidental wheel-scroll from changing the spinbox while the
    user is just scrolling the panel past it — same reasoning as the
    dungeons row_list's own _no_wheel helper."""
    widget.wheelEvent = lambda e: e.ignore()
    return widget


class _CategoryRow(QFrame):
    """One mob category entry — click to open the adjacent mob sub-panel."""

    clicked = Signal(str)

    def __init__(self, category_id: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 13px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(name_lbl, 1)
        arrow = QLabel("›")
        arrow.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
        lay.addWidget(arrow)

    def _apply_style(self):
        bg = "rgba(79,195,247,0.12)" if self._selected else "rgba(255,255,255,0.03)"
        border = Colors.ACCENT if self._selected else Colors.BORDER_SUBTLE
        self.setStyleSheet(f"""
            QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; }}
            QFrame:hover {{ background: rgba(255,255,255,0.08); }}
        """)

    def set_selected(self, sel: bool):
        self._selected = sel
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.category_id)
        super().mousePressEvent(event)


class SpawnPanel(QFrame):
    """Side panel for picking a mob category/mob and configuring the stamp."""

    PANEL_WIDTH = 300

    category_selected = Signal(str)  # category_id
    size_changed = Signal(float)
    quantity_changed = Signal(int)
    close_requested = Signal()
    content_changed = Signal()
    kind_changed = Signal(str)  # "mob" | "npc"

    _KIND_LABELS = {"mob": ("🐾", "MOBS", "SPAWN DE MOBS"), "npc": ("🧙", "NPCS", "SPAWN DE NPCS")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._category_rows: dict[str, _CategoryRow] = {}
        self._selected_category = ""
        self._active_kind = "mob"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header (outside scroll, always visible) ──
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        top_layout = QVBoxLayout(container)
        top_layout.setContentsMargins(10, 6, 10, 8)
        top_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._header_icon = QLabel("🐾")
        self._header_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(self._header_icon)
        self._header_title = QLabel("SPAWN DE MOBS")
        self._header_title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(self._header_title)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: #333; color: {Colors.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        top_layout.addLayout(header)

        # ── Mobs/NPCs toggle ──
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(4)
        self._kind_buttons: dict[str, QToolButton] = {}
        for kind in ("mob", "npc"):
            kind_icon, kind_label, _ = self._KIND_LABELS[kind]
            btn = QToolButton()
            btn.setText(f"{kind_icon} {kind_label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=kind: self._on_kind_clicked(k))
            toggle_row.addWidget(btn, 1)
            self._kind_buttons[kind] = btn
        top_layout.addLayout(toggle_row)
        self._apply_kind_button_styles()

        top_layout.addWidget(self._sep())

        self._top_container = container
        outer.addWidget(container)

        # ── Scrollable body: categories + selected-mob preview + stamp mode ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(10, 6, 10, 8)
        self._body_layout.setSpacing(6)

        cat_label = QLabel("CATEGORIAS")
        cat_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        self._body_layout.addWidget(cat_label)

        self._categories_col = QVBoxLayout()
        self._categories_col.setSpacing(4)
        self._body_layout.addLayout(self._categories_col)

        self._no_categories_label = QLabel("Nenhuma categoria de mob ainda — crie uma no painel Mobs.")
        self._no_categories_label.setWordWrap(True)
        self._no_categories_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        self._no_categories_label.hide()
        self._body_layout.addWidget(self._no_categories_label)

        self._body_layout.addWidget(self._sep())

        # ── Selected mob preview — live-updates with size/quantity ──
        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)
        self._preview_thumb = QLabel()
        self._preview_thumb.setFixedSize(_PREVIEW_SIZE, _PREVIEW_SIZE)
        self._preview_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_preview_placeholder_style()
        preview_row.addWidget(self._preview_thumb)
        preview_col = QVBoxLayout()
        preview_col.setSpacing(1)
        self._preview_name = QLabel("Nenhum mob selecionado")
        self._preview_name.setWordWrap(True)
        self._preview_name.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        preview_col.addWidget(self._preview_name)
        self._preview_hint = QLabel("Escolha uma categoria e um mob")
        self._preview_hint.setWordWrap(True)
        self._preview_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        preview_col.addWidget(self._preview_hint)
        preview_row.addLayout(preview_col, 1)
        self._body_layout.addLayout(preview_row)

        self._body_layout.addWidget(self._sep())

        # ── Modo Carimbo ──
        mode_label = QLabel("🖌 MODO CARIMBO")
        mode_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        self._body_layout.addWidget(mode_label)

        self.size_slider = BrushSlider("Tamanho", "⬤", 16, 200, 64, "px")
        self.size_slider.value_changed.connect(self.size_changed.emit)
        self._body_layout.addWidget(self.size_slider)

        qty_row = QHBoxLayout()
        qty_row.setSpacing(6)
        qty_label = QLabel("Quantidade")
        qty_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        qty_row.addWidget(qty_label)
        qty_row.addStretch()
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 30)
        self.quantity_spin.setValue(1)
        self.quantity_spin.setFixedWidth(60)
        self.quantity_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.quantity_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quantity_spin.setStyleSheet(f"""
            QSpinBox {{
                background: rgba(255,255,255,0.06); color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px; padding: 3px;
                font-size: 11px;
            }}
            QSpinBox:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        _no_wheel(self.quantity_spin)
        self.quantity_spin.valueChanged.connect(self.quantity_changed.emit)
        qty_row.addWidget(self.quantity_spin)
        self._body_layout.addLayout(qty_row)

        self._body_layout.addStretch()
        scroll.setWidget(body)
        self._body_widget = body
        outer.addWidget(scroll, 1)

    def content_height(self) -> int:
        """Natural height for this panel's actual content — header (outside
        the scroll area) plus the body's own natural height (inside it).
        PanelManager._content_height() alone only measures the first
        QScrollArea it finds, which would ignore the header entirely —
        same issue Região's own CRUD list panel had."""
        self._top_container.adjustSize()
        top_h = self._top_container.sizeHint().height()
        self._body_widget.adjustSize()
        body_h = self._body_widget.sizeHint().height()
        return top_h + body_h + 16

    def _on_kind_clicked(self, kind: str):
        if kind == self._active_kind:
            return
        self._active_kind = kind
        self._apply_kind_button_styles()
        icon, _, full_title = self._KIND_LABELS[kind]
        self._header_icon.setText(icon)
        self._header_title.setText(full_title)
        self._no_categories_label.setText(
            "Nenhuma categoria de mob ainda — crie uma no painel Mobs." if kind == "mob"
            else "Nenhuma categoria de NPC ainda — crie uma no painel NPCs."
        )
        self.kind_changed.emit(kind)

    def _apply_kind_button_styles(self):
        for kind, btn in self._kind_buttons.items():
            selected = kind == self._active_kind
            btn.setChecked(selected)
            bg = "rgba(79,195,247,0.16)" if selected else "rgba(255,255,255,0.03)"
            border = Colors.ACCENT if selected else Colors.BORDER_SUBTLE
            color = Colors.TEXT_PRIMARY if selected else Colors.TEXT_SECONDARY
            btn.setStyleSheet(f"""
                QToolButton {{
                    background: {bg}; color: {color}; border: 1px solid {border};
                    border-radius: 6px; padding: 5px 6px; font-size: 10px; font-weight: bold;
                }}
                QToolButton:hover {{ background: rgba(255,255,255,0.08); }}
            """)

    def _sep(self) -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _set_preview_placeholder_style(self):
        self._preview_thumb.setPixmap(QPixmap())
        self._preview_thumb.setStyleSheet(f"""
            background: rgba(255,255,255,0.05); border: 1px dashed {Colors.BORDER_SUBTLE};
            border-radius: {_PREVIEW_SIZE // 2}px;
        """)

    # ─── Public API (called by SpawnMediator) ───

    def set_categories(self, categories: list[tuple[str, str, str]]):
        """`categories` = [(id, icon, label), ...] — live from mob_categories."""
        for row in self._category_rows.values():
            self._categories_col.removeWidget(row)
            row.deleteLater()
        self._category_rows.clear()
        for cat_id, icon, label in categories:
            row = _CategoryRow(cat_id, icon, label)
            row.clicked.connect(self._on_category_clicked)
            self._categories_col.addWidget(row)
            self._category_rows[cat_id] = row
        self._no_categories_label.setVisible(not categories)

    def _on_category_clicked(self, category_id: str):
        self._selected_category = category_id
        for cid, row in self._category_rows.items():
            row.set_selected(cid == category_id)
        self.category_selected.emit(category_id)

    def set_selected_mob(self, name: str, preview_pixmap: QPixmap | None):
        empty_label = "Nenhum mob selecionado" if self._active_kind == "mob" else "Nenhum NPC selecionado"
        self._preview_name.setText(name or empty_label)
        self._preview_hint.setText("Clique no mapa para carimbar" if name else "Escolha uma categoria e um mob/NPC")
        if preview_pixmap and not preview_pixmap.isNull():
            self._preview_thumb.setStyleSheet("background: transparent; border: none;")
            self._preview_thumb.setPixmap(preview_pixmap)
        else:
            self._set_preview_placeholder_style()

    def paintEvent(self, event):
        paint_glass_panel(self)
