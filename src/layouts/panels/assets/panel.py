"""Asset Sound Manager — main panel orchestrating categories."""

from __future__ import annotations

from pathlib import Path

import shutil

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton,
    QLineEdit, QSizePolicy,
)
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.assets.card import CategorySection
from src.layouts.panels.assets.parallax_section import ParallaxPresetSection
from src.layouts.panels.assets.navigation_section import NavigationPresetSection
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.engines.assets.library import DEFAULT_STYLE, list_styles
from src.engines.map.parallax import get_parallax_library
from src.engines.map.navigation import get_navigation_library

_BG_CATEGORIES = [
    ("abstract", "🎨", "Abstract"),
    ("mystics", "🔮", "Mystics"),
    ("nature", "🌿", "Nature"),
    ("space", "🌌", "Space"),
    ("terrain", "🏜", "Terrain"),
]

_LIB = Path(__file__).resolve().parents[4] / "library"
_ASSETS_DIR = _LIB / "assets"
_BG_DIR = _LIB / "backgrounds"
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}

_CATEGORIES = [
    ("terrain", "🌍", "Terrain"),
    ("trees", "🌲", "Trees"),
    ("rocks", "🪨", "Rocks"),
    ("mountains", "⛰", "Mountains"),
    ("buildings", "🏠", "Buildings"),
    ("effects", "✨", "Effects"),
    ("misc", "📦", "Misc"),
]


class AssetSoundManager(QWidget):
    """Gerencia TODA a library — layout tabular com categorias colapsáveis.

    Categories are scoped to one "style" (Realistic/Cartoon/Pixel/...) at a
    time — library/assets/<style>/<category>/ — picked via a tab row that
    sits directly above them (same parent-of-categories pattern as
    AssetBrowserPanel's style tabs); switching it rebuilds the sections.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from src.services.asset_adjustments import AssetAdjustmentsService
        if not hasattr(AssetAdjustmentsService, '_instance'):
            AssetAdjustmentsService._instance = AssetAdjustmentsService()
        self._adj_service = AssetAdjustmentsService._instance
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._category_sections: list[CategorySection] = []
        self._new_category_row = None
        self._new_style_row = None
        self._notice_row = None
        self._build()

    def _build(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        main.addWidget(self._build_title_bar())
        main.addWidget(self._build_group_tabs())

        # Three mutually-exclusive content groups (only one visible at a
        # time) instead of one long stack of 17 sections — that flat list
        # repeated category names 2-3x (e.g. "Terrain" in Assets AND in
        # both background groups) and forced endless scrolling.
        self._assets_group = QWidget()
        self._assets_group.setStyleSheet("background: transparent;")
        self._assets_group_layout = QVBoxLayout(self._assets_group)
        self._assets_group_layout.setContentsMargins(0, 0, 0, 0)
        self._assets_group_layout.setSpacing(0)
        main.addWidget(self._assets_group)

        # Style tabs — parent of the category sections below, same pattern
        # as AssetBrowserPanel's style row (a tab, not a dropdown, so
        # picking a style stays visually anchored to what it controls).
        self._assets_group_layout.addWidget(self._build_style_tabs())

        # Categories — scoped to the selected style, rebuilt in place
        # whenever it changes.
        self._rebuild_category_sections()

        self._bg_images_group = self._build_bg_group("images", "")
        main.addWidget(self._bg_images_group)

        self._parallax_group = self._build_parallax_group()
        main.addWidget(self._parallax_group)

        self._navigation_group = self._build_navigation_group()
        main.addWidget(self._navigation_group)

        main.addStretch()
        self._show_group("assets")

    def _build_bg_group(self, subfolder: str, label_suffix: str) -> QWidget:
        group = QWidget()
        group.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for folder_name, icon, label in _BG_CATEGORIES:
            section = CategorySection(_BG_DIR / folder_name / subfolder, icon, f"{label}{label_suffix}")
            layout.addWidget(section)
        return group

    def _build_parallax_group(self) -> QWidget:
        group = QWidget()
        group.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # See ParallaxPresetSection's own setAlignment for why: without this,
        # a collapsed/removed preset can leave this group holding more
        # height than it currently needs, and QVBoxLayout centers the
        # header+list block inside that leftover space instead of pinning
        # it to the top — showing up as a gap below "Presets de Parallax".
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 0, 12, 0)
        h_lay.setSpacing(8)
        h_lbl = QLabel("🌄 Presets de Parallax")
        h_lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        h_lay.addWidget(h_lbl)
        h_lay.addStretch()
        add_preset_btn = QToolButton()
        add_preset_btn.setText("+ Novo Preset")
        add_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_preset_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; padding: 3px 8px; "
            f"color: {Colors.ACCENT}; font-size: 9pt; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        add_preset_btn.clicked.connect(self._add_parallax_preset)
        h_lay.addWidget(add_preset_btn)
        layout.addWidget(header)

        self._parallax_list_layout = QVBoxLayout()
        self._parallax_list_layout.setContentsMargins(8, 6, 8, 6)
        self._parallax_list_layout.setSpacing(6)
        self._parallax_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addLayout(self._parallax_list_layout)
        self._parallax_sections: dict[str, ParallaxPresetSection] = {}
        self._new_parallax_row = None

        for preset in get_parallax_library().list_presets():
            self._add_parallax_section(preset.key, preset.name)

        return group

    def _add_parallax_section(self, key: str, name: str):
        section = ParallaxPresetSection(key, name)
        section.delete_requested.connect(self._on_delete_parallax_preset)
        section.reorder_requested.connect(self._on_reorder_parallax_preset)
        self._parallax_list_layout.addWidget(section)
        self._parallax_sections[key] = section

    def _on_reorder_parallax_preset(self, from_key: str, to_key: str):
        get_parallax_library().reorder_preset(from_key, to_key)
        # Re-sync visual order to the library's (now-updated) order instead
        # of computing index math here — same "full rebuild from source of
        # truth" pattern the sections themselves use for their own rows.
        for preset in get_parallax_library().list_presets():
            section = self._parallax_sections.get(preset.key)
            if section is not None:
                self._parallax_list_layout.removeWidget(section)
                self._parallax_list_layout.addWidget(section)

    def _add_parallax_preset(self):
        """Same inline dashed-row creation pattern as _add_category/_add_style
        — no native dialog for naming the preset."""
        if getattr(self, "_new_parallax_row", None):
            self._new_parallax_row.findChild(QLineEdit).setFocus()
            return

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.03); border: 1px dashed {Colors.ACCENT};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 6, 8, 6)
        row_lay.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText("Nome do preset...")
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        row_lay.addWidget(edit, 1)

        confirm_btn = QToolButton()
        confirm_btn.setText("✓")
        confirm_btn.setFixedSize(22, 22)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        row_lay.addWidget(confirm_btn)

        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setFixedSize(22, 22)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        row_lay.addWidget(cancel_btn)

        confirm_btn.clicked.connect(lambda: self._confirm_new_parallax_preset(edit.text()))
        cancel_btn.clicked.connect(self._close_new_parallax_row)
        edit.returnPressed.connect(lambda: self._confirm_new_parallax_preset(edit.text()))

        self._parallax_list_layout.insertWidget(0, row)
        self._new_parallax_row = row
        edit.setFocus()

    def _close_new_parallax_row(self):
        if getattr(self, "_new_parallax_row", None):
            self._parallax_list_layout.removeWidget(self._new_parallax_row)
            self._new_parallax_row.deleteLater()
            self._new_parallax_row = None

    def _confirm_new_parallax_preset(self, name: str):
        name = name.strip()
        self._close_new_parallax_row()
        if not name:
            return
        preset = get_parallax_library().add_preset(name)
        self._add_parallax_section(preset.key, preset.name)

    def _on_delete_parallax_preset(self, key: str):
        get_parallax_library().remove_preset(key)
        section = self._parallax_sections.pop(key, None)
        if section:
            self._parallax_list_layout.removeWidget(section)
            section.deleteLater()

    def _build_navigation_group(self) -> QWidget:
        group = QWidget()
        group.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # See ParallaxPresetSection's own setAlignment for why: without this,
        # a collapsed/removed preset can leave this group holding more
        # height than it currently needs, and QVBoxLayout centers the
        # header+list block inside that leftover space instead of pinning
        # it to the top — showing up as a gap below "Presets de Navegação".
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 0, 12, 0)
        h_lay.setSpacing(8)
        h_lbl = QLabel("🧭 Presets de Navegação")
        h_lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        h_lay.addWidget(h_lbl)
        h_lay.addStretch()
        add_preset_btn = QToolButton()
        add_preset_btn.setText("+ Novo Preset")
        add_preset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_preset_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; padding: 3px 8px; "
            f"color: {Colors.ACCENT}; font-size: 9pt; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        add_preset_btn.clicked.connect(self._add_navigation_preset)
        h_lay.addWidget(add_preset_btn)
        layout.addWidget(header)

        self._navigation_list_layout = QVBoxLayout()
        self._navigation_list_layout.setContentsMargins(8, 6, 8, 6)
        self._navigation_list_layout.setSpacing(6)
        self._navigation_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addLayout(self._navigation_list_layout)
        self._navigation_sections: dict[str, NavigationPresetSection] = {}
        self._new_navigation_row = None

        for preset in get_navigation_library().list_presets():
            self._add_navigation_section(preset.key, preset.name)

        return group

    def _add_navigation_section(self, key: str, name: str):
        section = NavigationPresetSection(key, name)
        section.delete_requested.connect(self._on_delete_navigation_preset)
        section.reorder_requested.connect(self._on_reorder_navigation_preset)
        self._navigation_list_layout.addWidget(section)
        self._navigation_sections[key] = section

    def _on_reorder_navigation_preset(self, from_key: str, to_key: str):
        get_navigation_library().reorder_preset(from_key, to_key)
        for preset in get_navigation_library().list_presets():
            section = self._navigation_sections.get(preset.key)
            if section is not None:
                self._navigation_list_layout.removeWidget(section)
                self._navigation_list_layout.addWidget(section)

    def _add_navigation_preset(self):
        """Same inline dashed-row creation pattern as _add_parallax_preset —
        no native dialog for naming the preset."""
        if getattr(self, "_new_navigation_row", None):
            self._new_navigation_row.findChild(QLineEdit).setFocus()
            return

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.03); border: 1px dashed {Colors.ACCENT};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 6, 8, 6)
        row_lay.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText("Nome do preset...")
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        row_lay.addWidget(edit, 1)

        confirm_btn = QToolButton()
        confirm_btn.setText("✓")
        confirm_btn.setFixedSize(22, 22)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        row_lay.addWidget(confirm_btn)

        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setFixedSize(22, 22)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        row_lay.addWidget(cancel_btn)

        confirm_btn.clicked.connect(lambda: self._confirm_new_navigation_preset(edit.text()))
        cancel_btn.clicked.connect(self._close_new_navigation_row)
        edit.returnPressed.connect(lambda: self._confirm_new_navigation_preset(edit.text()))

        self._navigation_list_layout.insertWidget(0, row)
        self._new_navigation_row = row
        edit.setFocus()

    def _close_new_navigation_row(self):
        if getattr(self, "_new_navigation_row", None):
            self._navigation_list_layout.removeWidget(self._new_navigation_row)
            self._new_navigation_row.deleteLater()
            self._new_navigation_row = None

    def _confirm_new_navigation_preset(self, name: str):
        name = name.strip()
        self._close_new_navigation_row()
        if not name:
            return
        preset = get_navigation_library().add_preset(name)
        self._add_navigation_section(preset.key, preset.name)

    def _on_delete_navigation_preset(self, key: str):
        get_navigation_library().remove_preset(key)
        section = self._navigation_sections.pop(key, None)
        if section:
            self._navigation_list_layout.removeWidget(section)
            section.deleteLater()

    def _build_group_tabs(self) -> QFrame:
        container = QFrame()
        container.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        container.setSizePolicy(policy)
        container.setMinimumHeight(28)
        self._group_tab_flow = FlowLayout(container, spacing=2)
        self._group_tab_flow.setContentsMargins(10, 4, 10, 4)

        self._group_keys = ["assets", "bg_images", "parallax", "navigation"]
        self._group_labels = ["🎨 Assets", "🖼 Backgrounds Estáticos", "🌄 Parallax", "🧭 Navegação"]
        self._group_buttons: list[QToolButton] = []
        for i, label in enumerate(self._group_labels):
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background: transparent; color: {Colors.TEXT_SECONDARY};
                    padding: 4px 8px; font-size: 9pt; border: none;
                    border-bottom: 2px solid transparent;
                }}
                QToolButton:checked {{
                    color: {Colors.ACCENT}; border-bottom-color: {Colors.ACCENT};
                }}
                QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._on_group_tab_clicked(idx))
            self._group_tab_flow.addWidget(btn)
            self._group_buttons.append(btn)
        self._group_buttons[0].setChecked(True)

        return container

    def _build_style_tabs(self) -> QFrame:
        container = QFrame()
        container.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        container.setSizePolicy(policy)
        container.setMinimumHeight(26)
        self._style_tab_flow = FlowLayout(container, spacing=2)
        self._style_tab_flow.setContentsMargins(10, 4, 10, 4)
        self._style_keys: list[str] = []
        self._style_buttons: list[QToolButton] = []
        self._rebuild_style_tabs()

        return container

    def _rebuild_style_tabs(self):
        """Rebuilds the style tab row from list_styles() — the fixed 9
        slots plus any custom style folder the user created. Called after
        add/delete so newly created or removed styles show up immediately."""
        while self._style_tab_flow.count():
            item = self._style_tab_flow.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._style_buttons = []
        self._style_keys = list_styles()

        for i, key in enumerate(self._style_keys):
            btn = QToolButton()
            btn.setText(key.capitalize())
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background: transparent; color: {Colors.TEXT_SECONDARY};
                    padding: 3px 6px; font-size: 9pt; border: none;
                    border-bottom: 2px solid transparent;
                }}
                QToolButton:checked {{
                    color: {Colors.ACCENT}; border-bottom-color: {Colors.ACCENT};
                }}
                QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._on_style_tab_clicked(idx))
            self._style_tab_flow.addWidget(btn)
            self._style_buttons.append(btn)

        default_idx = self._style_keys.index(DEFAULT_STYLE) if DEFAULT_STYLE in self._style_keys else 0
        if self._style_buttons:
            self._style_buttons[default_idx].setChecked(True)

        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setFixedSize(18, 18)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Novo estilo")
        add_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        add_btn.clicked.connect(self._add_style)
        self._style_tab_flow.addWidget(add_btn)

        del_btn = QToolButton()
        del_btn.setText("✕")
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Excluir estilo atual")
        del_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 9px; font-size: 10px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        del_btn.clicked.connect(self._on_delete_style)
        self._style_tab_flow.addWidget(del_btn)

    def _select_style(self, key: str):
        idx = self._style_keys.index(key) if key in self._style_keys else 0
        for i, btn in enumerate(self._style_buttons):
            btn.setChecked(i == idx)
        self._rebuild_category_sections()

    def _on_style_tab_clicked(self, index: int):
        if index < len(self._style_keys):
            self._select_style(self._style_keys[index])

    def _on_group_tab_clicked(self, index: int):
        for i, btn in enumerate(self._group_buttons):
            btn.setChecked(i == index)
        self._show_group(self._group_keys[index])

    def _show_group(self, key: str):
        self._assets_group.setVisible(key == "assets")
        self._bg_images_group.setVisible(key == "bg_images")
        self._parallax_group.setVisible(key == "parallax")
        self._navigation_group.setVisible(key == "navigation")

    def showEvent(self, event):
        super().showEvent(event)
        # Tab buttons are built while the panel is still hidden, so
        # FlowLayout's first real pass never positions them — same gotcha
        # as AssetBrowserPanel's style/category tabs.
        self._group_tab_flow.invalidate()
        self._style_tab_flow.invalidate()

    def _build_title_bar(self) -> QFrame:
        title_frame = QFrame()
        title_frame.setFixedHeight(36)
        title_frame.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        t_lay = QHBoxLayout(title_frame)
        t_lay.setContentsMargins(12, 0, 12, 0)
        t_lay.setSpacing(8)

        t_lbl = QLabel("🎨 ASSETS")
        t_lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        t_lay.addWidget(t_lbl)

        self._total_lbl = QLabel("")
        self._total_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9pt; background: transparent; border: none;")
        t_lay.addWidget(self._total_lbl)
        t_lay.addStretch()

        # Style add/delete now live in the style tab row itself (see
        # _rebuild_style_tabs) — right next to what they act on, instead of
        # floating up here disconnected from the tabs below.
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setFixedSize(22, 22)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Nova categoria")
        add_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; "
            f"color: {Colors.ACCENT}; font-size: 14px; font-weight: bold; border-radius: 4px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        add_btn.clicked.connect(self._add_category)
        t_lay.addWidget(add_btn)

        return title_frame

    # ─── Style-scoped categories ────────────────────────────────────────

    def _current_style(self) -> str:
        idx = next((i for i, b in enumerate(self._style_buttons) if b.isChecked()), 0)
        return self._style_keys[idx] if idx < len(self._style_keys) else DEFAULT_STYLE

    def _rebuild_category_sections(self):
        for section in self._category_sections:
            self._assets_group_layout.removeWidget(section)
            section.deleteLater()
        self._category_sections.clear()

        style = self._current_style()
        for folder_name, icon, label in _CATEGORIES:
            section = CategorySection(_ASSETS_DIR / style / folder_name, icon, label)
            section.delete_requested.connect(self._remove_section)
            self._assets_group_layout.addWidget(section)
            self._category_sections.append(section)

        self._update_total()

    def _update_total(self):
        style_dir = _ASSETS_DIR / self._current_style()
        total = sum(
            1 for f in style_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        ) if style_dir.exists() else 0
        self._total_lbl.setText(f"({total})")

    def _add_category(self):
        """Reveals an inline "new category" card at the top of the list —
        no native/system popup, matches how CategorySection's own rename
        already swaps a label for a QLineEdit in place."""
        if getattr(self, "_new_category_row", None):
            self._new_category_row.findChild(QLineEdit).setFocus()
            return

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.03); border: 1px dashed {Colors.ACCENT};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 6, 8, 6)
        row_lay.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText("Nome da categoria...")
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        row_lay.addWidget(edit, 1)

        confirm_btn = QToolButton()
        confirm_btn.setText("✓")
        confirm_btn.setFixedSize(22, 22)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        row_lay.addWidget(confirm_btn)

        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setFixedSize(22, 22)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        row_lay.addWidget(cancel_btn)

        confirm_btn.clicked.connect(lambda: self._confirm_new_category(edit.text()))
        cancel_btn.clicked.connect(self._close_new_category_row)
        edit.returnPressed.connect(lambda: self._confirm_new_category(edit.text()))

        self._assets_group_layout.insertWidget(1, row)  # right after the style tabs
        self._new_category_row = row
        edit.setFocus()

    def _close_new_category_row(self):
        row = getattr(self, "_new_category_row", None)
        if row:
            self._assets_group_layout.removeWidget(row)
            row.deleteLater()
            self._new_category_row = None

    def _confirm_new_category(self, name: str):
        name = name.strip()
        self._close_new_category_row()
        if not name:
            return
        folder_name = name.lower().replace(" ", "_")
        style = self._current_style()
        folder = _ASSETS_DIR / style / folder_name
        if folder.exists():
            self._show_inline_notice(f"A categoria '{name}' já existe em {style.capitalize()}.")
            return
        folder.mkdir(parents=True, exist_ok=True)
        section = CategorySection(folder, "📁", name)
        section.delete_requested.connect(self._remove_section)
        self._assets_group_layout.addWidget(section)
        self._category_sections.append(section)
        self._update_total()

    def _on_delete_style(self):
        style = self._current_style()
        style_dir = _ASSETS_DIR / style
        assets = [
            f for f in style_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        ] if style_dir.exists() else []

        if assets:
            self._show_inline_notice(
                f"O estilo '{style.capitalize()}' possui {len(assets)} asset(s). "
                "Mova ou delete os assets antes de excluir o estilo."
            )
            return

        self._show_inline_notice(
            f"Excluir o estilo '{style.capitalize()}'? As categorias vazias dentro dele também são removidas.",
            on_confirm=lambda: self._do_delete_style(style),
        )

    def _do_delete_style(self, style: str):
        style_dir = _ASSETS_DIR / style
        if style_dir.exists():
            shutil.rmtree(style_dir, ignore_errors=True)

        # Deletion means the same thing for every style, shipped or custom —
        # the tab actually disappears (list_styles() no longer reports it,
        # since it's now derived from what's really on disk). Rebuilding
        # tabs BEFORE re-selecting, and selecting anything other than the
        # style we just deleted, matters: re-rendering the deleted style's
        # own categories would resurrect its folder via CategorySection's
        # lazy mkdir, undoing the deletion we just did.
        self._rebuild_style_tabs()
        remaining = self._style_keys
        if DEFAULT_STYLE in remaining:
            fallback = DEFAULT_STYLE
        elif remaining:
            fallback = remaining[0]
        else:
            fallback = DEFAULT_STYLE
        self._select_style(fallback)

    def _add_style(self):
        """Same inline-row creation pattern as _add_category, but for the
        style dimension itself — placed right below the style tab row."""
        if getattr(self, "_new_style_row", None):
            self._new_style_row.findChild(QLineEdit).setFocus()
            return

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(255,255,255,0.03); border: 1px dashed {Colors.ACCENT};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 6, 8, 6)
        row_lay.setSpacing(6)

        edit = QLineEdit()
        edit.setPlaceholderText("Nome do estilo...")
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.06); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 4px; color: {Colors.TEXT_PRIMARY}; font-size: 10pt;
                padding: 2px 6px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT}; }}
        """)
        row_lay.addWidget(edit, 1)

        confirm_btn = QToolButton()
        confirm_btn.setText("✓")
        confirm_btn.setFixedSize(22, 22)
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.ACCENT}; background: {Colors.ACCENT_DIM}; }}
            QToolButton:hover {{ background: rgba(79,195,247,0.3); }}
        """)
        row_lay.addWidget(confirm_btn)

        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setFixedSize(22, 22)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.ERROR}; background: rgba(239,83,80,0.2); }}
        """)
        row_lay.addWidget(cancel_btn)

        confirm_btn.clicked.connect(lambda: self._confirm_new_style(edit.text()))
        cancel_btn.clicked.connect(self._close_new_style_row)
        edit.returnPressed.connect(lambda: self._confirm_new_style(edit.text()))

        self._assets_group_layout.insertWidget(1, row)  # right after the style tabs
        self._new_style_row = row
        edit.setFocus()

    def _close_new_style_row(self):
        row = getattr(self, "_new_style_row", None)
        if row:
            self._assets_group_layout.removeWidget(row)
            row.deleteLater()
            self._new_style_row = None

    def _confirm_new_style(self, name: str):
        name = name.strip()
        self._close_new_style_row()
        if not name:
            return
        folder_name = name.lower().replace(" ", "_")
        folder = _ASSETS_DIR / folder_name
        if folder.exists():
            self._show_inline_notice(f"O estilo '{name}' já existe.")
            return
        folder.mkdir(parents=True, exist_ok=True)
        self._rebuild_style_tabs()
        self._select_style(folder_name)

    def _close_inline_notice(self):
        row = getattr(self, "_notice_row", None)
        if row:
            self._assets_group_layout.removeWidget(row)
            row.deleteLater()
            self._notice_row = None

    def _show_inline_notice(self, message: str, on_confirm=None):
        """In-panel banner replacing native QMessageBox popups — used for
        warnings and destructive-action confirmations (e.g. deleting a
        style), so nothing ever opens an OS-level window outside the app."""
        self._close_inline_notice()
        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: rgba(239,83,80,0.10); border: 1px solid {Colors.ERROR};
                border-radius: 6px;
            }}
        """)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 8, 8, 8)
        row_lay.setSpacing(8)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; background: transparent; border: none;")
        row_lay.addWidget(lbl, 1)

        if on_confirm:
            confirm_btn = QToolButton()
            confirm_btn.setText("Excluir")
            confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            confirm_btn.setStyleSheet(f"""
                QToolButton {{ border: none; border-radius: 4px; padding: 3px 10px; font-size: 9pt;
                    color: white; background: {Colors.ERROR}; }}
                QToolButton:hover {{ background: #ff6b66; }}
            """)
            def _confirm():
                self._close_inline_notice()
                on_confirm()
            confirm_btn.clicked.connect(_confirm)
            row_lay.addWidget(confirm_btn)

        dismiss_btn = QToolButton()
        dismiss_btn.setText("Cancelar" if on_confirm else "✕")
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setStyleSheet(f"""
            QToolButton {{ border: none; border-radius: 4px; padding: 3px 8px; font-size: 9pt;
                color: {Colors.TEXT_MUTED}; background: transparent; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; background: rgba(255,255,255,0.08); }}
        """)
        dismiss_btn.clicked.connect(self._close_inline_notice)
        row_lay.addWidget(dismiss_btn)

        self._assets_group_layout.insertWidget(1, row)
        self._notice_row = row

    def _remove_section(self, section: CategorySection):
        self._assets_group_layout.removeWidget(section)
        section.deleteLater()
        if section in self._category_sections:
            self._category_sections.remove(section)
        self._update_total()
