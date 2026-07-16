"""Asset Row Card & Category Section — individual asset cards and collapsible categories."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QToolButton, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage

from src.styles.tokens import Colors
from src.layouts.panels.assets.widgets import MiniSlider, SoundColumn, DropZone

_LIB = Path(__file__).resolve().parents[4] / "library"
_SOUNDS_DIR = _LIB / "sounds"
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}

_CARD_BG = "rgba(255, 255, 255, 0.03)"
_CARD_BORDER = "rgba(255, 255, 255, 0.08)"


class AssetRowCard(QFrame):
    """Card de um asset: [thumb+nome+meta+brilho/contraste] | [brush sound] | [ambient sound] [🗑]"""

    removed = Signal(str)
    settings_changed = Signal(str, int, int)

    def __init__(self, file_path: Path, category: str, parent=None):
        super().__init__(parent)
        self._path = file_path
        self._category = category
        self.setStyleSheet(
            f"QFrame {{ background: {_CARD_BG}; border: 1px solid {_CARD_BORDER}; border-radius: 6px; }}"
            f"QFrame:hover {{ border-color: rgba(255,255,255,0.15); background: rgba(255,255,255,0.04); }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(0)

        # ═══ 1/3: Info ═══
        col1 = QHBoxLayout()
        col1.setContentsMargins(0, 0, 0, 0)
        col1.setSpacing(8)

        self._thumb = QLabel()
        self._thumb.setFixedSize(40, 40)
        self._thumb.setStyleSheet("background: rgba(0,0,0,0.3); border-radius: 4px; border: none;")
        pix = QPixmap(str(file_path))
        if not pix.isNull():
            self._thumb.setPixmap(pix.scaled(QSize(40, 40), Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
            self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col1.addWidget(self._thumb, 0)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(2)

        self._name_label = QLabel(file_path.name)
        self._name_label.setFixedHeight(16)
        self._name_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 8pt; background: transparent; border: none; padding: 0;")
        self._name_label.setToolTip(file_path.name)
        name_row.addWidget(self._name_label)

        self._name_edit = QLineEdit(file_path.stem)
        self._name_edit.setFixedHeight(16)
        self._name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._name_edit.setStyleSheet(
            f"QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 8pt; "
            f"background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT}; "
            f"border-radius: 3px; padding: 0 4px; }}"
        )
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.hide()
        name_row.addWidget(self._name_edit)

        self._rename_btn = QToolButton()
        self._rename_btn.setText("✎")
        self._rename_btn.setFixedSize(14, 14)
        self._rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rename_btn.setToolTip("Renomear")
        self._rename_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; margin: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ACCENT}; }}"
        )
        self._rename_btn.clicked.connect(self._toggle_rename)
        name_row.addWidget(self._rename_btn)
        name_row.addStretch()
        self._renaming = False
        info.addLayout(name_row)

        size_kb = file_path.stat().st_size / 1024
        try:
            img = QImage(str(file_path))
            dims = f"{img.width()}x{img.height()}" if not img.isNull() else ""
        except Exception:
            dims = ""
        meta_text = f"{size_kb:.0f} KB"
        if dims:
            meta_text += f" \u2022 {dims}"
        meta_lbl = QLabel(meta_text)
        meta_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 7pt; background: transparent; border: none;")
        info.addWidget(meta_lbl)

        self._brightness = MiniSlider("Brilho", -100, 100, 0)
        self._brightness.value_changed.connect(self._update_preview)
        info.addWidget(self._brightness)
        self._contrast = MiniSlider("Contraste", -100, 100, 0)
        self._contrast.value_changed.connect(self._update_preview)
        info.addWidget(self._contrast)

        col1.addLayout(info, 1)
        row.addLayout(col1, 1)

        # ═══ 1/3: Brush Sound ═══
        col2 = QHBoxLayout()
        col2.setContentsMargins(0, 0, 0, 0)
        col2.setSpacing(0)
        col2.addStretch()
        asset_id = file_path.stem
        try:
            import sqlite3
            from src.engines.assets.library import LIBRARY_DB
            _db = sqlite3.connect(str(LIBRARY_DB))
            _db.row_factory = sqlite3.Row
            _row = _db.execute("SELECT id FROM assets WHERE source_path = ?", (str(file_path),)).fetchone()
            if _row:
                asset_id = _row["id"]
            _db.close()
        except Exception:
            pass
        brush_dir = _SOUNDS_DIR / "brush" / asset_id
        self._brush_sound = SoundColumn(brush_dir, prefix="paint")
        col2.addWidget(self._brush_sound)
        col2.addStretch()
        row.addLayout(col2, 1)

        # ═══ 1/3: Ambient Sound ═══
        col3 = QHBoxLayout()
        col3.setContentsMargins(0, 0, 0, 0)
        col3.setSpacing(0)
        col3.addStretch()
        ambient_dir = _SOUNDS_DIR / "brush" / asset_id
        self._ambient_sound = SoundColumn(ambient_dir, prefix="ambient")
        col3.addWidget(self._ambient_sound)
        col3.addStretch()
        row.addLayout(col3, 1)

        # ═══ Delete ═══
        del_btn = QToolButton()
        del_btn.setText("\U0001f5d1")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 12px; "
            f"color: {Colors.TEXT_MUTED}; border-radius: 12px; }}"
            f"QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}"
        )
        del_btn.clicked.connect(self._on_delete)
        row.addWidget(del_btn, 0)

    def _update_preview(self):
        from src.services.asset_adjustments import apply_brightness_contrast
        b = self._brightness.value()
        c = self._contrast.value()
        img = QImage(str(self._path))
        if img.isNull():
            return
        img = img.scaled(QSize(40, 40), Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        img = apply_brightness_contrast(img, b, c)
        self._thumb.setPixmap(QPixmap.fromImage(img))
        self.settings_changed.emit(str(self._path), b, c)

    def _toggle_rename(self):
        if not self._renaming:
            self._name_edit.setText(self._path.stem)
            self._name_label.hide()
            self._name_edit.show()
            self._name_edit.setFocus()
            self._name_edit.selectAll()
            self._renaming = True
        else:
            self._finish_rename()

    def _finish_rename(self):
        new_name = self._name_edit.text().strip()
        if new_name and new_name != self._path.stem:
            new_path = self._path.parent / (new_name + self._path.suffix)
            if not new_path.exists():
                self._path.rename(new_path)
                self._path = new_path
                self._name_label.setText(new_path.name)
                self._name_label.setToolTip(new_path.name)
        self._name_edit.hide()
        self._name_label.show()
        self._renaming = False

    def _on_delete(self):
        self._path.unlink(missing_ok=True)
        self.removed.emit(str(self._path))
        self.deleteLater()

    def get_settings(self) -> dict:
        return {
            "path": str(self._path),
            "brightness": self._brightness.value(),
            "contrast": self._contrast.value(),
            "brush_sound": self._brush_sound.get_config(),
            "ambient_sound": self._ambient_sound.get_config(),
        }


class CategorySection(QWidget):
    """Seção colapsável para uma categoria — header + cards dos assets."""

    def __init__(self, folder: Path, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._icon = icon
        self._label = label
        self._expanded = False
        self._renaming = False
        self.setStyleSheet("background: transparent;")
        self.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # Header
        self._header = QFrame()
        self._header.setFixedHeight(32)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.02); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        self._header.mousePressEvent = lambda e: self._toggle()

        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 0, 10, 0)
        h_lay.setSpacing(0)

        col1_hdr = QHBoxLayout()
        col1_hdr.setSpacing(4)
        col1_hdr.setContentsMargins(0, 0, 0, 0)
        col1_hdr.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._arrow = QLabel("▶")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 8px; background: transparent; border: none;")
        col1_hdr.addWidget(self._arrow)

        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        col1_hdr.addWidget(ic)

        self._title_label = QLabel(label)
        self._title_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none; padding: 0;"
        )
        col1_hdr.addWidget(self._title_label)

        self._rename_btn = QToolButton()
        self._rename_btn.setText("✎")
        self._rename_btn.setFixedSize(14, 14)
        self._rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rename_btn.setToolTip("Renomear categoria")
        self._rename_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; margin: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ACCENT}; }}"
        )
        self._rename_btn.clicked.connect(self._toggle_rename)
        col1_hdr.addWidget(self._rename_btn)

        self._title_edit = QLineEdit(label)
        self._title_edit.setFixedHeight(20)
        self._title_edit.setMaximumWidth(100)
        self._title_edit.setStyleSheet(
            f"QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT}; "
            f"border-radius: 3px; padding: 0 4px; }}"
        )
        self._title_edit.returnPressed.connect(self._finish_rename)
        self._title_edit.hide()
        col1_hdr.addWidget(self._title_edit)

        self._count_lbl = QLabel("(0)")
        self._count_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        col1_hdr.addWidget(self._count_lbl)
        col1_hdr.addStretch()
        h_lay.addLayout(col1_hdr, 1)

        self._brush_hdr = QLabel("🖌 Brush")
        self._brush_hdr.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._brush_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brush_hdr.hide()
        h_lay.addWidget(self._brush_hdr, 1)

        self._ambient_hdr = QLabel("🔊 Sounds")
        self._ambient_hdr.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._ambient_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ambient_hdr.hide()
        h_lay.addWidget(self._ambient_hdr, 1)

        main.addWidget(self._header)

        # Content
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent; border: none;")
        self._content.hide()
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(8, 6, 8, 6)
        self._content_lay.setSpacing(6)

        self._populate()
        main.addWidget(self._content)

    def _populate(self):
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._folder.mkdir(parents=True, exist_ok=True)
        files = sorted(
            f for f in self._folder.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        )
        self._count_lbl.setText(f"({len(files)})")

        for f in files:
            card = AssetRowCard(f, self._label)
            card.removed.connect(lambda _: self._refresh())
            card.settings_changed.connect(self._on_adjustment)
            self._content_lay.addWidget(card)

        drop = DropZone(self._folder, _SUPPORTED_IMG)
        drop.files_dropped.connect(self._on_dropped)
        self._content_lay.addWidget(drop)

    def _toggle_rename(self):
        if not self._renaming:
            self._title_edit.setText(self._label)
            self._title_label.hide()
            self._title_edit.show()
            self._title_edit.setFocus()
            self._title_edit.selectAll()
            self._renaming = True
        else:
            self._finish_rename()

    def _finish_rename(self):
        new_name = self._title_edit.text().strip()
        if new_name and new_name != self._label:
            new_folder = self._folder.parent / new_name.lower().replace(" ", "_")
            if not new_folder.exists():
                self._folder.rename(new_folder)
                self._folder = new_folder
                self._label = new_name
                self._title_label.setText(new_name)
        self._title_edit.hide()
        self._title_label.show()
        self._renaming = False

    def _on_adjustment(self, path: str, b: int, c: int):
        from src.services.asset_adjustments import AssetAdjustmentsService
        if hasattr(AssetAdjustmentsService, '_instance'):
            AssetAdjustmentsService._instance.set(path, b, c)

    def _on_dropped(self, paths: list):
        idx = self._content_lay.count() - 1
        for p in paths:
            card = AssetRowCard(p, self._label)
            card.removed.connect(lambda _: self._refresh())
            self._content_lay.insertWidget(idx, card)
            idx += 1
        self._refresh()

    def _refresh(self):
        count = len([
            f for f in self._folder.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        ])
        self._count_lbl.setText(f"({count})")

    def _toggle(self):
        self._expanded = not self._expanded
        self._arrow.setText("▼" if self._expanded else "▶")
        self._content.setVisible(self._expanded)
        self._brush_hdr.setVisible(self._expanded)
        self._ambient_hdr.setVisible(self._expanded)
