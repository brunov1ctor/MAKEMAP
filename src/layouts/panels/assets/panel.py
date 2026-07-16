"""Asset Sound Manager — main panel orchestrating categories."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

from src.styles.tokens import Colors
from src.layouts.panels.assets.card import CategorySection

_LIB = Path(__file__).resolve().parents[4] / "library"
_ASSETS_DIR = _LIB / "assets"
_BG_DIR = _LIB / "backgrounds"
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}


class AssetSoundManager(QWidget):
    """Gerencia TODA a library — layout tabular com categorias colapsáveis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from src.services.asset_adjustments import AssetAdjustmentsService
        if not hasattr(AssetAdjustmentsService, '_instance'):
            AssetAdjustmentsService._instance = AssetAdjustmentsService()
        self._adj_service = AssetAdjustmentsService._instance
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build()

    def _build(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Title bar
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
        main.addWidget(title_frame)

        # Categories
        categories = [
            ("terrain", "🌍", "Terrain"),
            ("trees", "🌲", "Trees"),
            ("rocks", "🪨", "Rocks"),
            ("mountains", "⛰", "Mountains"),
            ("buildings", "🏠", "Buildings"),
            ("effects", "✨", "Effects"),
            ("misc", "📦", "Misc"),
        ]
        for folder_name, icon, label in categories:
            section = CategorySection(_ASSETS_DIR / folder_name, icon, label)
            main.addWidget(section)

        # Backgrounds — Images
        main.addWidget(self._section_title("🖼 BACKGROUNDS — Imagens"))
        bg_categories = [
            ("abstract", "🎨", "Abstract"),
            ("mystics", "🔮", "Mystics"),
            ("nature", "🌿", "Nature"),
            ("space", "🌌", "Space"),
            ("terrain", "🏜", "Terrain"),
        ]
        for folder_name, icon, label in bg_categories:
            section = CategorySection(_BG_DIR / folder_name / "images", icon, label)
            main.addWidget(section)

        # Backgrounds — GIFs
        main.addWidget(self._section_title("🎞 BACKGROUNDS — Animados (GIF/MP4)"))
        for folder_name, icon, label in bg_categories:
            section = CategorySection(_BG_DIR / folder_name / "gifs", icon, f"{label} GIFs")
            main.addWidget(section)

        # Total count
        total = sum(
            1 for f in _ASSETS_DIR.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        )
        self._total_lbl.setText(f"({total})")
        main.addStretch()

    def _section_title(self, text: str) -> QFrame:
        frame = QFrame()
        frame.setFixedHeight(36)
        frame.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        lay.addWidget(lbl)
        lay.addStretch()
        return frame
