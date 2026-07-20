"""Background Section — color picker, image/gif browser for terrain panel."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QWidget, QScrollArea, QLineEdit, QGridLayout, QTabBar, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize, QFileSystemWatcher
from PySide6.QtGui import QColor, QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.terrain.color_picker import HueBar, SatValSquare, ColorSlider
from src.layouts.panels.brush.flow_layout import FlowLayout


class BackgroundSection(QFrame):
    """Background customization section: color, image, or gif."""

    background_changed = Signal(str, str)  # type, value
    close_requested = Signal()
    content_changed = Signal()  # emitted when visible content changes (expand/collapse)

    def __init__(self, bg_dir: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self._bg_dir = bg_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        # No own "Plano de Fundo" header row — TerrainSettingsPanel now
        # wraps this whole widget in a CollapsibleSection titled that,
        # so a second inner label here would just duplicate it.

        # Toggle buttons
        bg_row = QHBoxLayout()
        bg_row.setSpacing(6)
        self._bg_buttons: dict[str, QToolButton] = {}
        self._bg_active: str = ""

        for key, icon_text, tooltip in [
            ("color", "🎨", "Cor fixa"),
            ("image", "🖼", "Imagem estática"),
            ("parallax", "🌄", "Parallax (camadas)"),
        ]:
            btn = QToolButton()
            btn.setText(icon_text)
            btn.setToolTip(tooltip)
            btn.setFixedSize(48, 32)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._bg_btn_style())
            btn.clicked.connect(lambda checked, k=key: self._on_bg_toggle(k))
            bg_row.addWidget(btn)
            self._bg_buttons[key] = btn
        bg_row.addStretch()
        layout.addLayout(bg_row)

        # Color picker widget
        self._bg_color_widget = QFrame()
        self._bg_color_widget.setStyleSheet("background: transparent; border: none;")
        color_lay = QVBoxLayout(self._bg_color_widget)
        color_lay.setContentsMargins(0, 4, 0, 4)
        color_lay.setSpacing(6)

        self._hue_bar = HueBar()
        self._hue_bar.setFixedHeight(16)
        self._hue_bar.hue_changed.connect(self._on_hue_changed)
        color_lay.addWidget(self._hue_bar)

        self._sv_square = SatValSquare()
        self._sv_square.setFixedHeight(100)
        self._sv_square.sv_changed.connect(self._on_sv_changed)
        color_lay.addWidget(self._sv_square)

        self._r_slider = ColorSlider("R", 0, 255, 7)
        self._g_slider = ColorSlider("G", 0, 255, 17)
        self._b_slider = ColorSlider("B", 0, 255, 31)
        self._r_slider.value_changed.connect(self._on_rgb_slider_changed)
        self._g_slider.value_changed.connect(self._on_rgb_slider_changed)
        self._b_slider.value_changed.connect(self._on_rgb_slider_changed)
        color_lay.addWidget(self._r_slider)
        color_lay.addWidget(self._g_slider)
        color_lay.addWidget(self._b_slider)

        # Hex + Preview
        hex_row = QHBoxLayout()
        hex_row.setSpacing(4)
        hex_label = QLabel("#")
        hex_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        hex_row.addWidget(hex_label)
        self._hex_input = QLineEdit("07111F")
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
        hex_row.addWidget(self._hex_input)

        self._bg_color_swatch = QLabel()
        self._bg_color_swatch.setFixedSize(22, 22)
        self._bg_color_swatch.setStyleSheet("background: #07111F; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);")
        hex_row.addWidget(self._bg_color_swatch)
        hex_row.addStretch()
        color_lay.addLayout(hex_row)

        # Basic colors palette
        basic_label = QLabel("Cores básicas")
        basic_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        color_lay.addWidget(basic_label)

        palette_grid = QGridLayout()
        palette_grid.setSpacing(3)
        self._color_palette = [
            "#000000", "#434343", "#666666", "#999999", "#b7b7b7", "#cccccc", "#d9d9d9", "#efefef", "#f3f3f3", "#ffffff",
            "#980000", "#ff0000", "#ff9900", "#ffff00", "#00ff00", "#00ffff", "#4a86e8", "#0000ff", "#9900ff", "#ff00ff",
            "#e6b8af", "#f4cccc", "#fce5cd", "#fff2cc", "#d9ead3", "#d0e0e3", "#c9daf8", "#cfe2f3", "#d9d2e9", "#ead1dc",
            "#dd7e6b", "#ea9999", "#f9cb9c", "#ffe599", "#b6d7a8", "#a2c4c9", "#a4c2f4", "#9fc5e8", "#b4a7d6", "#d5a6bd",
            "#cc4125", "#e06666", "#f6b26b", "#ffd966", "#93c47d", "#76a5af", "#6d9eeb", "#6fa8dc", "#8e7cc3", "#c27ba0",
        ]
        self._bg_selected_color = "#07111F"
        for i, c in enumerate(self._color_palette):
            swatch = QLabel()
            swatch.setFixedSize(18, 18)
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            swatch.setStyleSheet(f"background: {c}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.15);")
            swatch.mousePressEvent = lambda e, color=c: self._select_bg_color(color)
            palette_grid.addWidget(swatch, i // 10, i % 10)
        color_lay.addLayout(palette_grid)

        # Custom colors
        custom_label = QLabel("Cores personalizadas")
        custom_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        color_lay.addWidget(custom_label)

        self._custom_colors_layout = QHBoxLayout()
        self._custom_colors_layout.setSpacing(3)
        self._custom_color_slots: list[QLabel] = []
        self._custom_color_data: list[str] = [""] * 10
        for i in range(10):
            slot = QLabel()
            slot.setFixedSize(18, 18)
            slot.setCursor(Qt.CursorShape.PointingHandCursor)
            slot.setStyleSheet(f"background: rgba(255,255,255,0.06); border-radius: 3px; border: 1px dashed {Colors.BORDER_SUBTLE};")
            slot.mousePressEvent = lambda e, idx=i: self._on_custom_slot_click(idx)
            self._custom_colors_layout.addWidget(slot)
            self._custom_color_slots.append(slot)
        self._custom_colors_layout.addStretch()
        color_lay.addLayout(self._custom_colors_layout)

        add_custom_btn = QToolButton()
        add_custom_btn.setText("+ Adicionar às personalizadas")
        add_custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_custom_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; font-size: 9px; color: {Colors.ACCENT};
                background: transparent; padding: 2px;
            }}
            QToolButton:hover {{ color: {Colors.ACCENT_HOVER}; }}
        """)
        add_custom_btn.clicked.connect(self._add_to_custom_colors)
        color_lay.addWidget(add_custom_btn)

        self._bg_color_widget.hide()
        self._hsv = [0, 100, 100]
        layout.addWidget(self._bg_color_widget)

        # File browser widget (image/gif)
        self._bg_file_widget = QFrame()
        self._bg_file_widget.setStyleSheet("background: transparent; border: none;")
        file_lay = QVBoxLayout(self._bg_file_widget)
        file_lay.setContentsMargins(0, 4, 0, 4)
        file_lay.setSpacing(4)

        self._bg_tabs = QTabBar()
        self._bg_tabs.setExpanding(False)
        self._bg_tabs.setStyleSheet(f"""
            QTabBar::tab {{
                background: transparent; color: {Colors.TEXT_SECONDARY};
                padding: 3px 6px; font-size: 9px; border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {Colors.ACCENT}; border-bottom-color: {Colors.ACCENT};
            }}
            QTabBar::tab:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        self._bg_tabs.wheelEvent = lambda e: e.ignore()
        self._bg_categories = ["space", "terrain", "mystics", "nature", "abstract"]
        for cat in self._bg_categories:
            self._bg_tabs.addTab(cat.capitalize())
        self._bg_tabs.currentChanged.connect(self._on_bg_tab_changed)
        file_lay.addWidget(self._bg_tabs)

        self._bg_grid_scroll = QScrollArea()
        self._bg_grid_scroll.setWidgetResizable(True)
        self._bg_grid_scroll.setMinimumHeight(80)
        self._bg_grid_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._bg_grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._bg_grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._bg_grid_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._bg_grid_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{
                width: 3px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.TEXT_MUTED}; border-radius: 1px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self._bg_grid_container = QWidget()
        self._bg_grid_container.setStyleSheet("background: transparent;")
        self._bg_grid_layout = FlowLayout(self._bg_grid_container, spacing=4)
        self._bg_grid_layout.setContentsMargins(4, 4, 4, 4)
        self._bg_grid_scroll.setWidget(self._bg_grid_container)
        file_lay.addWidget(self._bg_grid_scroll)

        self._bg_file_label = QLabel("Nenhum selecionado")
        self._bg_file_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        file_lay.addWidget(self._bg_file_label)

        self._bg_file_widget.hide()
        self._bg_asset_buttons: list[QFrame] = []
        layout.addWidget(self._bg_file_widget)

        # Parallax preset picker — lists presets managed in the Config
        # panel (AssetSoundManager's Parallax group), not raw files.
        self._bg_parallax_widget = QFrame()
        self._bg_parallax_widget.setStyleSheet("background: transparent; border: none;")
        parallax_lay = QVBoxLayout(self._bg_parallax_widget)
        parallax_lay.setContentsMargins(0, 4, 0, 4)
        parallax_lay.setSpacing(4)
        self._bg_parallax_list_layout = parallax_lay
        self._bg_parallax_hint = QLabel("Nenhum preset — crie um no painel Config")
        self._bg_parallax_hint.setWordWrap(True)
        self._bg_parallax_hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        parallax_lay.addWidget(self._bg_parallax_hint)
        self._bg_parallax_widget.hide()
        layout.addWidget(self._bg_parallax_widget)

        # Watcher
        self._bg_watcher = QFileSystemWatcher(self)
        for cat in self._bg_categories:
            sub_path = os.path.join(self._bg_dir, cat, "images")
            os.makedirs(sub_path, exist_ok=True)
            self._bg_watcher.addPath(sub_path)
        self._bg_watcher.directoryChanged.connect(self._on_bg_dir_changed)
        self._bg_current_category = self._bg_categories[0]

    # ─── Style helpers ───

    def _bg_btn_style(self) -> str:
        return f"""
            QToolButton {{
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px;
                font-size: 16px; color: {Colors.TEXT_SECONDARY};
                background: rgba(255,255,255,0.04);
            }}
            QToolButton:hover {{
                background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY};
            }}
            QToolButton:checked {{
                background: {Colors.ACCENT_DIM}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
        """

    # ─── Toggle logic ───

    def _on_bg_toggle(self, key: str):
        btn = self._bg_buttons[key]
        if self._bg_active == key:
            btn.setChecked(False)
            self._bg_active = ""
            self._bg_color_widget.hide()
            self._bg_file_widget.hide()
            self._bg_parallax_widget.hide()
            self.background_changed.emit("none", "")
        else:
            for k, b in self._bg_buttons.items():
                b.setChecked(k == key)
            self._bg_active = key
            self._bg_color_widget.hide()
            self._bg_file_widget.hide()
            self._bg_parallax_widget.hide()
            if key == "color":
                self._bg_color_widget.show()
                # Re-activating "Cor fixa" after it was toggled off (which
                # clears the background to "none") must restore the last
                # picked color immediately, not wait for the user to touch
                # a slider/swatch again.
                self.background_changed.emit("color", self._bg_selected_color)
            elif key == "image":
                self._bg_file_widget.show()
                current_idx = self._bg_tabs.currentIndex()
                self._load_bg_assets(self._bg_categories[current_idx])
            elif key == "parallax":
                self._bg_parallax_widget.show()
                self._load_parallax_presets()
        self.content_changed.emit()

    # ─── Color logic ───

    def _select_bg_color(self, color: str):
        self._bg_selected_color = color
        self._bg_color_swatch.setStyleSheet(
            f"background: {color}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self._hex_input.setText(color.lstrip("#"))
        qc = QColor(color)
        self._hsv = [qc.hsvHue() if qc.hsvHue() >= 0 else 0, qc.hsvSaturation() * 100 // 255, qc.value() * 100 // 255]
        self._hue_bar.set_hue(self._hsv[0])
        self._sv_square.set_hue(self._hsv[0])
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._r_slider.set_value(qc.red())
        self._g_slider.set_value(qc.green())
        self._b_slider.set_value(qc.blue())
        self.background_changed.emit("color", color)
        self.close_requested.emit()

    def _on_hue_changed(self, hue: int):
        self._hsv[0] = hue
        self._sv_square.set_hue(hue)
        self._apply_hsv()

    def _on_sv_changed(self, s: int, v: int):
        self._hsv[1] = s
        self._hsv[2] = v
        self._apply_hsv()

    def _on_rgb_slider_changed(self, _val: int):
        r = self._r_slider.value()
        g = self._g_slider.value()
        b = self._b_slider.value()
        color = QColor(r, g, b)
        hex_str = color.name()
        self._bg_selected_color = hex_str
        self._bg_color_swatch.setStyleSheet(
            f"background: {hex_str}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self._hex_input.setText(hex_str.lstrip("#"))
        h = color.hsvHue() if color.hsvHue() >= 0 else 0
        self._hsv = [h, color.hsvSaturation() * 100 // 255, color.value() * 100 // 255]
        self._hue_bar.blockSignals(True)
        self._hue_bar.set_hue(h)
        self._hue_bar.blockSignals(False)
        self._sv_square.blockSignals(True)
        self._sv_square.set_hue(h)
        self._sv_square.set_sv(self._hsv[1], self._hsv[2])
        self._sv_square.blockSignals(False)
        self.background_changed.emit("color", hex_str)

    def _apply_hsv(self):
        color = QColor.fromHsv(self._hsv[0], self._hsv[1] * 255 // 100, self._hsv[2] * 255 // 100)
        hex_str = color.name()
        self._bg_selected_color = hex_str
        self._bg_color_swatch.setStyleSheet(
            f"background: {hex_str}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"
        )
        self._hex_input.setText(hex_str.lstrip("#"))
        self._r_slider.blockSignals(True)
        self._g_slider.blockSignals(True)
        self._b_slider.blockSignals(True)
        self._r_slider.set_value(color.red())
        self._g_slider.set_value(color.green())
        self._b_slider.set_value(color.blue())
        self._r_slider.blockSignals(False)
        self._g_slider.blockSignals(False)
        self._b_slider.blockSignals(False)
        self.background_changed.emit("color", hex_str)

    def _on_hex_entered(self):
        text = self._hex_input.text().strip().lstrip("#")
        if len(text) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in text):
            self._select_bg_color(f"#{text}")

    def _add_to_custom_colors(self):
        for i, c in enumerate(self._custom_color_data):
            if not c:
                self._custom_color_data[i] = self._bg_selected_color
                self._custom_color_slots[i].setStyleSheet(
                    f"background: {self._bg_selected_color}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2);"
                )
                return
        self._custom_color_data[0] = self._bg_selected_color
        self._custom_color_slots[0].setStyleSheet(
            f"background: {self._bg_selected_color}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2);"
        )

    def _on_custom_slot_click(self, idx: int):
        if self._custom_color_data[idx]:
            self._select_bg_color(self._custom_color_data[idx])

    # ─── File browser logic ───

    def _on_bg_tab_changed(self, index: int):
        if index >= len(self._bg_categories):
            return
        category = self._bg_categories[index]
        self._bg_current_category = category
        self._load_bg_assets(category)

    def _on_bg_dir_changed(self, path: str):
        if self._bg_file_widget.isVisible():
            self._load_bg_assets(self._bg_current_category)

    def _load_bg_assets(self, category: str):
        for w in self._bg_asset_buttons:
            w.deleteLater()
        self._bg_asset_buttons.clear()

        cat_dir = os.path.join(self._bg_dir, category)
        if not os.path.isdir(cat_dir):
            os.makedirs(cat_dir, exist_ok=True)
            return

        scan_dir = os.path.join(cat_dir, "images")
        extensions = (".png", ".jpg", ".jpeg", ".bmp", ".webp")

        os.makedirs(scan_dir, exist_ok=True)
        files = sorted(f for f in os.listdir(scan_dir) if f.lower().endswith(extensions))

        for fname in files:
            fpath = os.path.join(scan_dir, fname)

            item_widget = QFrame()
            item_widget.setFixedSize(56, 62)
            item_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            item_widget.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                    background: rgba(255,255,255,0.04); padding: 1px;
                }}
                QFrame:hover {{ border-color: {Colors.TEXT_SECONDARY}; }}
            """)
            item_lay = QVBoxLayout(item_widget)
            item_lay.setContentsMargins(2, 2, 2, 2)
            item_lay.setSpacing(1)

            thumb_label = QLabel()
            thumb_label.setFixedSize(36, 36)
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_label.setStyleSheet("background: transparent; border: none;")
            pix = self._get_thumbnail(fpath)
            if pix and not pix.isNull():
                thumb_label.setPixmap(pix)
            else:
                thumb_label.setText("🖼")
                thumb_label.setStyleSheet("font-size: 18px; background: transparent; border: none;")
            item_lay.addWidget(thumb_label, 0, Qt.AlignmentFlag.AlignCenter)

            name_lbl = QLabel(fname[:8])
            name_lbl.setFixedHeight(12)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 7px; background: transparent; border: none;")
            item_lay.addWidget(name_lbl)

            item_widget.mousePressEvent = lambda e, p=fpath, w=item_widget: self._on_bg_item_clicked(p, w)
            item_widget.setToolTip(fname)

            self._bg_grid_layout.addWidget(item_widget)
            self._bg_asset_buttons.append(item_widget)

    def _get_thumbnail(self, fpath: str) -> QPixmap | None:
        pix = QPixmap(fpath)
        if not pix.isNull():
            return pix.scaled(QSize(36, 36), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        return None

    # ─── Parallax preset picker ───

    def _load_parallax_presets(self):
        while self._bg_parallax_list_layout.count() > 1:  # keep the hint label
            item = self._bg_parallax_list_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        from src.engines.map.parallax import get_parallax_library
        presets = get_parallax_library().list_presets()
        self._bg_parallax_hint.setVisible(not presets)

        for preset in presets:
            btn = QToolButton()
            btn.setText(f"🌄 {preset.name}  ({len(preset.layers)} camadas)")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                    background: rgba(255,255,255,0.04); color: {Colors.TEXT_PRIMARY};
                    font-size: 10px; padding: 4px 8px; text-align: left;
                }}
                QToolButton:hover {{ background: {Colors.PANEL_HOVER}; border-color: {Colors.ACCENT}; }}
            """)
            btn.clicked.connect(lambda checked=False, key=preset.key: self._on_parallax_preset_clicked(key))
            self._bg_parallax_list_layout.addWidget(btn)

    def _on_parallax_preset_clicked(self, preset_key: str):
        self.background_changed.emit("parallax", preset_key)
        self.close_requested.emit()

    def _on_bg_item_clicked(self, path: str, widget: QFrame):
        for w in self._bg_asset_buttons:
            w.setStyleSheet(f"""
                QFrame {{
                    border: 2px solid {Colors.BORDER_SUBTLE}; border-radius: 4px;
                    background: rgba(255,255,255,0.04); padding: 1px;
                }}
                QFrame:hover {{ border-color: {Colors.TEXT_SECONDARY}; }}
            """)
        widget.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {Colors.ACCENT}; border-radius: 4px;
                background: {Colors.ACCENT_DIM}; padding: 1px;
            }}
        """)
        self._bg_file_label.setText(os.path.basename(path))
        self.background_changed.emit(self._bg_active, path)
        self.close_requested.emit()
