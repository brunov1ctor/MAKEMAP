"""New-tab/tree creation panel — swaps places with the canvas in
SkillTreeCanvas._stack, the same pattern as CategoryEditPanel
(mobs/category_edit_panel.py).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QPushButton,
    QLineEdit, QSizePolicy, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal

from src.styles.tokens import Colors
from src.layouts.panels.mobs.edit_widgets import _CatalogPickerDialog
from src.layouts.panels.shared.entity_panel.category_edit_panel import _ColorSwatch, _SharedColorPicker


class _TreeTabCreatePanel(QFrame):
    """Painel de criação de uma nova aba/árvore — troca de lugar com o
    canvas (ver SkillTreeCanvas._stack), o mesmo padrão do CategoryEditPanel
    (mobs/category_edit_panel.py): nome da aba + habilidade inicial,
    escolhida num picker de catálogo (mesma UI de "+ Vincular Habilidade"
    das informações extras de mobs). Sem QDialog, sem QMessageBox."""

    save_requested = Signal(str, dict, str, str)  # (tab_name, initial_skill, theme_color, text_color)
    close_requested = Signal()

    # Narrowest width this panel is ever asked to render at (matches
    # light/edit_panel.py's fixed width — the tightest existing precedent
    # for a panel that also hosts _SharedColorPicker's RGB slider rows).
    # Without this floor, squeezing the host splitter column below it (see
    # panel.py's per-column setMinimumWidth(250) for _skill_tree, which
    # this panel swaps in for) clips the RGB value labels ("79", "137")
    # past the frame's right edge instead of scrolling.
    PANEL_WIDTH = 280

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMinimumWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._catalog_provider = lambda: []
        self._picked_skill: dict | None = None
        self._color_target: str | None = None  # "theme" | "text" | None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Same scroll-wrap pattern as CategoryEditPanel/SkillEditor/
        # ItemEditor — the color picker (hue bar + 3 RGB rows + preview)
        # can make this panel taller than a short/small monitor can show;
        # this scrolls instead of clipping.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            f"QScrollBar:vertical {{ width: 4px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}"
        )
        root.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        scroll.setWidget(container)

        outer = QVBoxLayout(container)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("NOVA ABA")
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        header.addWidget(title)
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
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        outer.addLayout(header)

        name_lbl = QLabel("Nome da aba")
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Ex.: Fogo, Terra, Água…")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; padding: 4px 6px; }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        self._name_edit.textEdited.connect(lambda _t: self._set_error(""))
        outer.addWidget(self._name_edit)

        skill_lbl = QLabel("Habilidade inicial")
        skill_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(skill_lbl)
        self._skill_btn = QPushButton("Escolher habilidade inicial")
        self._skill_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skill_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 6px 10px;
                font-size: 10px; text-align: left; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._skill_btn.clicked.connect(self._on_pick_skill)
        outer.addWidget(self._skill_btn)

        # Cor tema/borda — mesma UI (um _SharedColorPicker por baixo de dois
        # _ColorSwatch) da criação de categoria de mob (CategoryEditPanel).
        # Vira o padrão do chip da aba, da borda e do texto dos nós dessa
        # guia (ver SkillTreeCanvas._active_theme_color/_active_text_color).
        theme_lbl = QLabel("Cor do tema (opcional)")
        theme_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        outer.addWidget(theme_lbl)
        swatches_row = QHBoxLayout()
        swatches_row.setSpacing(8)
        self._theme_swatch = _ColorSwatch("Tema / Borda")
        self._theme_swatch.clicked.connect(lambda: self._activate_color_target("theme"))
        self._theme_swatch.cleared.connect(lambda: self._on_swatch_cleared("theme"))
        swatches_row.addWidget(self._theme_swatch, 1)
        self._text_swatch = _ColorSwatch("Texto do Nó")
        self._text_swatch.clicked.connect(lambda: self._activate_color_target("text"))
        self._text_swatch.cleared.connect(lambda: self._on_swatch_cleared("text"))
        swatches_row.addWidget(self._text_swatch, 1)
        outer.addLayout(swatches_row)

        self._color_picker = _SharedColorPicker()
        self._color_picker.color_changed.connect(self._on_shared_color_changed)
        self._color_picker.hide()
        outer.addWidget(self._color_picker)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color: {Colors.ERROR}; font-size: 9px; background: transparent; border: none;")
        self._error_lbl.hide()
        outer.addWidget(self._error_lbl)

        outer.addStretch()

        self._save_btn = QToolButton()
        self._save_btn.setText("✓ Criar Aba")
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setMinimumHeight(32)
        self._save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._save_btn.setStyleSheet(f"""
            QToolButton {{ background: {Colors.SUCCESS}; border: none; border-radius: 6px;
                color: white; font-size: 11px; font-weight: bold; }}
            QToolButton:hover {{ background: #7bc97e; }}
        """)
        self._save_btn.clicked.connect(self._on_save_clicked)
        outer.addWidget(self._save_btn)

    def set_catalog_provider(self, provider):
        self._catalog_provider = provider

    def load(self):
        self._name_edit.clear()
        self._picked_skill = None
        self._skill_btn.setText("Escolher habilidade inicial")
        self._theme_swatch.set_color("")
        self._text_swatch.set_color("")
        self._color_picker.hide()
        self._color_target = None
        self._set_error("")
        self._name_edit.setFocus()

    def _set_error(self, message: str):
        self._error_lbl.setText(message)
        self._error_lbl.setVisible(bool(message))

    def _swatch_for_target(self, target: str) -> _ColorSwatch:
        return {"theme": self._theme_swatch, "text": self._text_swatch}[target]

    def _activate_color_target(self, target: str):
        """Clicar num swatch carrega a cor dele no único picker compartilhado
        e o mostra; clicar de novo no MESMO swatch (picker já aberto nele)
        só fecha — mesmo padrão de CategoryEditPanel._activate_color_target."""
        if self._color_target == target and self._color_picker.isVisible():
            self._color_picker.hide()
            self._color_target = None
            return
        self._color_target = target
        self._color_picker.set_color(self._swatch_for_target(target).color())
        self._color_picker.show()

    def _on_shared_color_changed(self, hex_color: str):
        if self._color_target:
            self._swatch_for_target(self._color_target).set_color(hex_color)

    def _on_swatch_cleared(self, target: str):
        if target == self._color_target:
            self._color_picker.hide()
            self._color_target = None

    def _on_pick_skill(self):
        dlg = _CatalogPickerDialog("Habilidade Inicial", "Buscar habilidade", self._catalog_provider(), parent=self)
        picked_id = dlg.exec()
        if not picked_id:
            return
        skill = next((sk for sk in self._catalog_provider() if sk.get("id") == picked_id), None)
        if not skill:
            return
        self._picked_skill = skill
        self._skill_btn.setText(f"{skill.get('icon') or '✨'}  {skill.get('name', '—')}")
        self._set_error("")

    def _on_save_clicked(self):
        name = self._name_edit.text().strip()
        if not name:
            self._set_error("Digite um nome para a aba.")
            self._name_edit.setFocus()
            return
        if not self._picked_skill:
            self._set_error("Escolha a habilidade inicial.")
            return
        self.save_requested.emit(name, self._picked_skill, self._theme_swatch.color(), self._text_swatch.color())
