"""Asset Sound Manager — main panel orchestrating categories."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton, QInputDialog, QMessageBox
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
        main.addWidget(title_frame)
        self._assets_layout = main  # referência para inserir novas seções antes do stretch

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
            section.delete_requested.connect(self._remove_section)
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

    def _add_category(self):
        name, ok = QInputDialog.getText(self, "Nova Categoria", "Nome da categoria:")
        if not ok or not name.strip():
            return
        folder_name = name.strip().lower().replace(" ", "_")
        folder = _ASSETS_DIR / folder_name
        if folder.exists():
            QMessageBox.warning(self, "Já existe", f"A categoria '{name}' já existe.")
            return
        folder.mkdir(parents=True, exist_ok=True)
        section = CategorySection(folder, "📁", name.strip())
        section.delete_requested.connect(self._remove_section)
        # insere antes do stretch (last item)
        idx = self._assets_layout.count() - 1
        self._assets_layout.insertWidget(idx, section)
        total = sum(1 for f in _ASSETS_DIR.rglob("*") if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG)
        self._total_lbl.setText(f"({total})")

    def _remove_section(self, section: CategorySection):
        self._assets_layout.removeWidget(section)
        section.deleteLater()
        total = sum(1 for f in _ASSETS_DIR.rglob("*") if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG)
        self._total_lbl.setText(f"({total})")

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
