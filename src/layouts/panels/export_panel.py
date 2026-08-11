"""Export Panel — floating toolbar panel to export the map as a PNG image,
choosing the exported area (map bounds vs. current viewport) and an optional
decorative frame (solid color/line-style/rounded corners, or an imported
frame image). Opened from the canvas toolbar's "Exportar" action, same
PanelManager-registered pattern as Grid/Terrain/Region/Light/Background."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
    QToolButton, QScrollArea, QWidget, QComboBox, QFileDialog, QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors, combo_qss
from src.layouts.panel_manager import paint_glass_panel


class ExportPanel(QFrame):

    PANEL_WIDTH = 300

    export_requested = Signal(dict)  # options dict, see map_exporter.export_map_image
    close_requested = Signal()
    content_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self._area = "bounds"
        self._format = "png"
        self._transparent_bg = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._container = container
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(8)

        # ─── Header ───
        header = QHBoxLayout()
        header.setSpacing(6)
        icon = QLabel("📤")
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        header.addWidget(icon)
        title = QLabel("Exportar")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;
            background: transparent; border: none;
        """)
        header.addWidget(title)
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
        layout.addLayout(header)

        layout.addWidget(self._separator())

        # ─── Área ───
        layout.addWidget(self._section_label("ÁREA DE EXPORTAÇÃO"))
        area_row = QHBoxLayout()
        area_row.setSpacing(8)
        self._area_cards: dict[str, QFrame] = {}
        for key, icon, title, desc in [
            ("bounds", "🗺", "Limite do mapa", "Exporta todo o mapa visível"),
            ("viewport", "🖥", "Viewport atual", "Exporta apenas o que está na tela"),
        ]:
            card = self._build_area_card(key, icon, title, desc)
            area_row.addWidget(card, 1)
            self._area_cards[key] = card
        self._on_area_changed("bounds")
        layout.addLayout(area_row)

        layout.addWidget(self._separator())

        # ─── Fundo ───
        layout.addWidget(self._section_label("FUNDO"))
        self._transparent_check = QCheckBox("Fundo transparente")
        self._transparent_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._transparent_check.setStyleSheet(f"""
            QCheckBox {{
                color: {Colors.TEXT_SECONDARY}; font-size: 11px;
                background: transparent; border: none; spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 1px solid {Colors.BORDER_SUBTLE}; background: rgba(255,255,255,0.06);
            }}
            QCheckBox::indicator:checked {{ background: {Colors.ACCENT}; border-color: {Colors.ACCENT}; }}
        """)
        self._transparent_check.toggled.connect(self._on_transparent_toggled)
        layout.addWidget(self._transparent_check)

        layout.addWidget(self._separator())

        # ─── Pré-visualização ───
        layout.addWidget(self._section_label("PRÉ-VISUALIZAÇÃO"))
        preview_note = QLabel("A visualização pode não representar o tamanho final.")
        preview_note.setWordWrap(True)
        preview_note.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 9px;
            background: transparent; border: none;
        """)
        layout.addWidget(preview_note)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setFixedHeight(120)
        self._preview_label.setWordWrap(True)
        self.set_preview_pixmap(None)
        layout.addWidget(self._preview_label)

        layout.addWidget(self._separator())

        # ─── Formato ───
        layout.addWidget(self._section_label("Formato"))
        self._format_combo = QComboBox()
        for value, label in [("png", "PNG"), ("jpg", "JPG"), ("pdf", "PDF")]:
            self._format_combo.addItem(label, value)
        self._format_combo.currentIndexChanged.connect(
            lambda i: setattr(self, "_format", self._format_combo.currentData()))
        self._format_combo.setStyleSheet(combo_qss())
        layout.addWidget(self._format_combo)

        layout.addWidget(self._separator())

        # ─── Exportar ───
        export_btn = QToolButton()
        export_btn.setText("Exportar…")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet(f"""
            QToolButton {{
                background: {Colors.ACCENT}; border: none; border-radius: 6px;
                color: #06222E; font-size: 12px; font-weight: bold; padding: 8px;
            }}
            QToolButton:hover {{ background: {Colors.ACCENT_HOVER}; }}
        """)
        export_btn.clicked.connect(self._on_export_clicked)
        layout.addWidget(export_btn)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ─── UI helpers ───

    def _separator(self) -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.10); border: none;")
        return sep

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        return lbl

    def _build_area_card(self, key: str, icon: str, title: str, desc: str) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 15px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;
            background: transparent; border: none;
        """)
        lay.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"""
            color: {Colors.TEXT_MUTED}; font-size: 9px;
            background: transparent; border: none;
        """)
        lay.addWidget(desc_lbl)

        card.mousePressEvent = lambda event, k=key: self._on_area_changed(k)
        return card

    def _style_area_card(self, card: QFrame, selected: bool):
        if selected:
            card.setStyleSheet(f"""
                QFrame {{
                    background: {Colors.ACCENT_DIM}; border: 1px solid {Colors.ACCENT};
                    border-radius: 6px;
                }}
            """)
        else:
            card.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: 6px;
                }}
                QFrame:hover {{ border-color: {Colors.BORDER_HOVER}; }}
            """)

    # ─── Área ───

    def _on_area_changed(self, key: str):
        self._area = key
        for k, card in self._area_cards.items():
            self._style_area_card(card, k == key)
        self.content_changed.emit()

    # ─── Fundo ───

    def _on_transparent_toggled(self, checked: bool):
        self._transparent_bg = checked
        self.content_changed.emit()

    # ─── Pré-visualização ───

    def set_preview_pixmap(self, pixmap: QPixmap | None):
        if pixmap is None or pixmap.isNull():
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("Sem pré-visualização")
            self._preview_label.setStyleSheet(f"""
                QLabel {{
                    background: rgba(0,0,0,0.2); border: 1px solid {Colors.BORDER_SUBTLE};
                    border-radius: 6px; color: {Colors.TEXT_MUTED}; font-size: 10px;
                }}
            """)
            return
        self._preview_label.setText("")
        self._preview_label.setStyleSheet(f"""
            QLabel {{
                background: rgba(0,0,0,0.2); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px;
            }}
        """)
        target_w = self._preview_label.width() or (self.PANEL_WIDTH - 20)
        target_h = self._preview_label.height() or 120
        scaled = pixmap.scaled(
            target_w, target_h,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._preview_label.setPixmap(scaled)

    # ─── Exportar ───

    _FORMAT_FILTERS = {
        "png": "Imagem PNG (*.png)",
        "jpg": "Imagem JPG (*.jpg)",
        "pdf": "Documento PDF (*.pdf)",
    }

    def set_frame_options_fn(self, fn):
        """Callable que retorna o dict de moldura do BrushToolPanel."""
        self._frame_options_fn = fn

    def current_options(self) -> dict:
        """Export/preview options — everything map_exporter needs except
        save_path (only real exports have one)."""
        opts = {
            "area": self._area,
            "format": self._format,
            "transparent_bg": self._transparent_bg,
        }
        if hasattr(self, "_frame_options_fn") and self._frame_options_fn:
            opts.update(self._frame_options_fn())
        return opts

    def _on_export_clicked(self):
        import os
        fmt = self._format
        downloads = Path(os.path.expanduser("~")) / "Downloads"
        default_path = str(downloads / f"mapa.{fmt}")
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Mapa", default_path, self._FORMAT_FILTERS[fmt])
        if not save_path:
            return
        if not save_path.lower().endswith(f".{fmt}"):
            save_path += f".{fmt}"
        options = self.current_options()
        options["save_path"] = save_path
        self.export_requested.emit(options)

    def paintEvent(self, event):
        paint_glass_panel(self)
