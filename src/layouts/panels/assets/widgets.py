"""Asset Manager Widgets — MiniSlider, SoundColumn, DropZone."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import ClassVar

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QSlider, QToolButton, QFileDialog, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.styles.tokens import Colors

_SUPPORTED_SND = {".wav", ".mp3", ".ogg", ".flac"}
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}

_SHARED_BORDER = "1px solid rgba(255, 183, 77, 0.9)"   # laranja para "compartilhado"
_SHARED_BG     = "rgba(255, 183, 77, 0.08)"


def _file_hash(path: str) -> str:
    """SHA-256 primeiros 16 chars do arquivo de som."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return ""


class SoundRegistry:
    """Singleton que rastreia SoundColumns pelo hash do arquivo de som."""
    _hash_to_cols: ClassVar[dict[str, set[SoundColumn]]] = {}

    @classmethod
    def register(cls, col: SoundColumn, file_hash: str):
        if not file_hash:
            return
        cls._hash_to_cols.setdefault(file_hash, set()).add(col)
        cls._refresh_group(file_hash)

    @classmethod
    def unregister(cls, col: SoundColumn, file_hash: str):
        if not file_hash or file_hash not in cls._hash_to_cols:
            return
        cls._hash_to_cols[file_hash].discard(col)
        cls._refresh_group(file_hash)

    @classmethod
    def _refresh_group(cls, file_hash: str):
        cols = {c for c in cls._hash_to_cols.get(file_hash, set()) if c._sound_hash == file_hash}
        cls._hash_to_cols[file_hash] = cols
        shared = len(cols) > 1
        for c in cols:
            c._set_shared_style(shared)

    @classmethod
    def propagate_rename(cls, file_hash: str, new_display: str, source: SoundColumn):
        """Atualiza o nome exibido em todos os peers do mesmo hash."""
        for c in list(cls._hash_to_cols.get(file_hash, set())):
            if c is not source:
                c._apply_display_name(new_display)


class MiniSlider(QWidget):
    """Label + slider compacto inline."""
    value_changed = Signal(int)

    def __init__(self, label: str, min_v: int = -100, max_v: int = 100, default: int = 0, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        lbl = QLabel(label)
        lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 7pt; background: transparent; border: none;")
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(min_v, max_v)
        self._slider.setValue(default)
        self._slider.setMinimumWidth(40)
        self._slider.setMaximumWidth(80)
        self._slider.setStyleSheet(
            f"QSlider {{ background: transparent; }}"
            f"QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ width: 10px; height: 10px; margin: -3px 0; "
            f"background: {Colors.ACCENT}; border-radius: 5px; }}"
            f"QSlider::sub-page:horizontal {{ background: {Colors.ACCENT_DIM}; border-radius: 2px; }}"
        )
        self._slider.valueChanged.connect(self.value_changed.emit)
        lay.addWidget(self._slider, 1)

        self._val = QLabel(str(default))
        self._val.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self._val.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 7pt; background: transparent; border: none;")
        self._val.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._slider.valueChanged.connect(lambda v: self._val.setText(str(v)))
        lay.addWidget(self._val)

    def value(self) -> int:
        return self._slider.value()


class SoundColumn(QWidget):
    """Coluna de som: lê/escreve em asset_sounds no banco."""

    def __init__(self, asset_id: str, prefix: str, parent=None):
        super().__init__(parent)
        self._asset_id = asset_id
        self._prefix = prefix
        self._sound_path: str = ""
        self._sound_hash: str = ""
        self._player: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None
        self.setStyleSheet("background: transparent; border: none;")
        self.setAcceptDrops(True)

        # carrega do banco
        saved_volume = 70
        display_name = ""
        try:
            from src.engines.assets.library import LIBRARY_DB
            db = sqlite3.connect(str(LIBRARY_DB))
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT path, volume, display_name FROM asset_sounds WHERE asset_id=? AND prefix=?",
                (asset_id, prefix)
            ).fetchone()
            db.close()
            if row:
                self._sound_path = row["path"] if Path(row["path"]).exists() else ""
                saved_volume = int(row["volume"] * 100)
                display_name = row["display_name"]
        except Exception:
            pass

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # ── linha 1: ícone + play + volume ──
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)

        self._drop_frame = QFrame()
        self._drop_frame.setFixedSize(32, 32)
        self._drop_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drop_frame.setAcceptDrops(True)
        self._drop_idle()

        drop_lay = QVBoxLayout(self._drop_frame)
        drop_lay.setContentsMargins(0, 0, 0, 0)
        drop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._drop_icon = QLabel("🔊")
        self._drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        drop_lay.addWidget(self._drop_icon)

        # label minúsculo dentro do frame (mantido para compatibilidade mas vazio)
        self._drop_label = QLabel("")
        self._drop_label.hide()

        self._clear_btn = QToolButton(self._drop_frame)
        self._clear_btn.setText("✕")
        self._clear_btn.setFixedSize(12, 12)
        self._clear_btn.move(20, 0)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            f"QToolButton {{ background: rgba(0,0,0,0.6); border: none; font-size: 6px; "
            f"color: {Colors.TEXT_MUTED}; border-radius: 6px; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        self._clear_btn.clicked.connect(self._clear_sound)
        self._clear_btn.hide()

        self._drop_frame.mousePressEvent = self._on_click_drop
        top.addWidget(self._drop_frame)

        self._play_btn = QToolButton()
        self._play_btn.setText("▶")
        self._play_btn.setFixedSize(16, 16)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.ACCENT_DIM}; border: none; font-size: 7px; "
            f"color: {Colors.ACCENT}; border-radius: 8px; }}"
            f"QToolButton:hover {{ background: rgba(79,195,247,0.3); }}"
        )
        self._play_btn.clicked.connect(self._preview)
        top.addWidget(self._play_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(saved_volume)
        self._vol.setMaximumWidth(60)
        self._vol.setStyleSheet(
            f"QSlider {{ background: transparent; }}"
            f"QSlider::groove:horizontal {{ height: 3px; background: rgba(255,255,255,0.1); border-radius: 1px; }}"
            f"QSlider::handle:horizontal {{ width: 8px; height: 8px; margin: -3px 0; "
            f"background: {Colors.TEXT_SECONDARY}; border-radius: 4px; }}"
            f"QSlider::sub-page:horizontal {{ background: rgba(255,255,255,0.2); border-radius: 1px; }}"
        )
        self._vol.valueChanged.connect(self._on_volume_changed)
        top.addWidget(self._vol, 1)
        lay.addLayout(top)

        # ── linha 2: nome estilo asset (label + botão ✎ + edit oculto) ──
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(2)

        self._name_label = QLabel("sem som")
        self._name_label.setFixedHeight(16)
        self._name_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 8pt; "
            f"background: transparent; border: none; padding: 0;"
        )
        name_row.addWidget(self._name_label)

        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(16)
        self._name_edit.setStyleSheet(
            f"QLineEdit {{ color: {Colors.TEXT_PRIMARY}; font-size: 8pt; "
            f"background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT}; "
            f"border-radius: 3px; padding: 0 4px; }}"
        )
        self._name_edit.returnPressed.connect(self._on_rename)
        self._name_edit.editingFinished.connect(self._on_rename)
        self._name_edit.hide()
        name_row.addWidget(self._name_edit)

        self._rename_btn = QToolButton()
        self._rename_btn.setText("✎")
        self._rename_btn.setFixedSize(14, 14)
        self._rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rename_btn.setToolTip("Renomear som")
        self._rename_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; font-size: 11px; "
            f"color: {Colors.TEXT_MUTED}; padding: 0; margin: 0; }}"
            f"QToolButton:hover {{ color: {Colors.ACCENT}; }}"
        )
        self._rename_btn.clicked.connect(self._toggle_rename)
        self._rename_btn.hide()
        name_row.addWidget(self._rename_btn)
        name_row.addStretch()
        lay.addLayout(name_row)
        self._renaming = False

        if self._sound_path:
            self._sound_hash = _file_hash(self._sound_path)
            self._apply_display_name(display_name or Path(self._sound_path).stem)
            self._clear_btn.show()
            self._drop_filled()
            SoundRegistry.register(self, self._sound_hash)

    def _on_volume_changed(self, value: int):
        if self._sound_path:
            self._save_to_db(self._sound_path, value / 100.0, self._name_label.text())

    def _save_to_db(self, path: str, volume: float, display_name: str):
        try:
            from src.engines.assets.library import LIBRARY_DB
            db = sqlite3.connect(str(LIBRARY_DB))
            db.execute(
                """INSERT INTO asset_sounds (asset_id, prefix, path, volume, display_name)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(asset_id, prefix) DO UPDATE SET
                       path=excluded.path, volume=excluded.volume, display_name=excluded.display_name""",
                (self._asset_id, self._prefix, path, volume, display_name)
            )
            db.commit()
            db.close()
        except Exception:
            pass

    def _drop_idle(self):
        self._drop_frame.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); "
            f"border: 1px dashed {Colors.BORDER_SUBTLE}; border-radius: 4px; }}"
        )

    def _drop_highlight(self):
        self._drop_frame.setStyleSheet(
            f"QFrame {{ background: rgba(79,195,247,0.1); "
            f"border: 1px dashed {Colors.ACCENT}; border-radius: 4px; }}"
        )

    def _drop_filled(self):
        self._drop_frame.setStyleSheet(
            f"QFrame {{ background: rgba(79,195,247,0.06); "
            f"border: 1px solid {Colors.ACCENT_DIM}; border-radius: 4px; }}"
        )

    def _set_sound(self, path: str):
        if self._sound_hash:
            SoundRegistry.unregister(self, self._sound_hash)
            self._sound_hash = ""
        self._sound_path = path
        if path:
            self._sound_hash = _file_hash(path)
            stem = Path(path).stem
            if self._prefix and stem.lower().startswith(self._prefix + "_"):
                stem = stem[len(self._prefix) + 1:]
            self._apply_display_name(stem)
            self._clear_btn.show()
            self._drop_filled()
            self._save_to_db(path, self._vol.value() / 100.0, stem)
            SoundRegistry.register(self, self._sound_hash)
        else:
            self._apply_display_name("")
            self._clear_btn.hide()
            self._drop_idle()
            self._set_shared_style(False)
            try:
                from src.engines.assets.library import LIBRARY_DB
                db = sqlite3.connect(str(LIBRARY_DB))
                db.execute(
                    "DELETE FROM asset_sounds WHERE asset_id=? AND prefix=?",
                    (self._asset_id, self._prefix)
                )
                db.commit()
                db.close()
            except Exception:
                pass

    def _apply_display_name(self, name: str):
        self._name_edit.blockSignals(True)
        if name:
            self._name_label.setText(name)
            self._name_label.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: 8pt; "
                f"background: transparent; border: none; padding: 0;"
            )
            self._name_edit.setText(name)
            self._rename_btn.show()
        else:
            self._name_label.setText("sem som")
            self._name_label.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 8pt; "
                f"background: transparent; border: none; padding: 0;"
            )
            self._name_edit.clear()
            self._rename_btn.hide()
        self._name_label.show()
        self._name_edit.hide()
        self._renaming = False
        self._name_edit.blockSignals(False)

    def _toggle_rename(self):
        if not self._renaming:
            self._name_edit.setText(self._name_label.text())
            self._name_label.hide()
            self._name_edit.show()
            self._name_edit.setFocus()
            self._name_edit.selectAll()
            self._renaming = True
        else:
            self._on_rename()

    def _on_name_dblclick(self, event):
        pass  # substituido por _toggle_rename

    def _set_shared_style(self, shared: bool):
        """Borda laranja quando o som é compartilhado com outro asset."""
        if shared:
            self._drop_frame.setStyleSheet(
                f"QFrame {{ background: {_SHARED_BG}; border: {_SHARED_BORDER}; border-radius: 4px; }}"
            )
        else:
            if self._sound_path:
                self._drop_filled()
            else:
                self._drop_idle()

    def _on_rename(self):
        if not self._renaming:
            return
        new_name = self._name_edit.text().strip()
        self._name_edit.blockSignals(True)
        self._name_edit.hide()
        self._name_label.show()
        self._renaming = False
        self._name_edit.blockSignals(False)
        if not new_name or not self._sound_path:
            return
        old = Path(self._sound_path)
        new_filename = f"{self._prefix}_{new_name}{old.suffix}" if self._prefix else f"{new_name}{old.suffix}"
        new_path = old.parent / new_filename
        if new_path != old and not new_path.exists():
            old.rename(new_path)
            self._sound_path = str(new_path)
        self._name_label.setText(new_name)
        self._name_label.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 8pt; "
            f"background: transparent; border: none; padding: 0;"
        )
        self._save_to_db(self._sound_path, self._vol.value() / 100.0, new_name)
        SoundRegistry.propagate_rename(self._sound_hash, new_name, self)

    def _clear_sound(self):
        self._set_sound("")

    def _on_click_drop(self, event):
        exts = ' '.join('*' + e for e in _SUPPORTED_SND)
        file, _ = QFileDialog.getOpenFileName(self, "Selecionar Som", "", f"Sons ({exts})")
        if file:
            dest = self._import_sound(Path(file))
            self._set_sound(str(dest))

    def _import_sound(self, src: Path) -> Path:
        from src.engines.assets.library import LIBRARY_DIR
        dest_dir = LIBRARY_DIR / "sounds" / "brush" / self._asset_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = src.name
        if self._prefix and not name.lower().startswith(self._prefix):
            name = f"{self._prefix}_{name}"
        dest = dest_dir / name
        if not dest.exists():
            shutil.copy2(src, dest)
        return dest

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            if any(Path(u.toLocalFile()).suffix.lower() in _SUPPORTED_SND for u in event.mimeData().urls()):
                event.acceptProposedAction()
                self._drop_highlight()

    def dragLeaveEvent(self, event):
        if self._sound_path:
            self._drop_filled()
        else:
            self._drop_idle()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            src = Path(url.toLocalFile())
            if src.is_file() and src.suffix.lower() in _SUPPORTED_SND:
                dest = self._import_sound(src)
                self._set_sound(str(dest))
                break
        event.acceptProposedAction()

    def _preview(self):
        if not self._sound_path:
            return
        if self._player:
            self._player.stop()
        self._output = QAudioOutput()
        self._output.setVolume(self._vol.value() / 100.0)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._output)
        self._player.setSource(QUrl.fromLocalFile(str(Path(self._sound_path).resolve())))
        self._player.play()

    def get_config(self) -> dict:
        return {"sound": self._sound_path, "volume": self._vol.value() / 100.0}


class DropZone(QFrame):
    """Drop zone para adicionar novos assets."""

    files_dropped = Signal(list)

    def __init__(self, target_dir: Path, extensions: set, parent=None):
        super().__init__(parent)
        self._target = target_dir
        self._extensions = extensions
        self.setAcceptDrops(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._idle()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("＋ Novo Asset (arraste ou clique)")
        lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 8pt; background: transparent; border: none;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        self.mousePressEvent = self._on_click

    def _idle(self):
        self.setStyleSheet(
            f"QFrame {{ background: rgba(79, 195, 247, 0.06); border: 1px dashed rgba(79, 195, 247, 0.35); border-radius: 6px; }}"
        )

    def _on_click(self, event):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Assets", "",
            f"Imagens ({' '.join('*' + e for e in self._extensions)})"
        )
        if files:
            self._import_files([Path(f) for f in files])

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            if any(Path(u.toLocalFile()).suffix.lower() in self._extensions for u in event.mimeData().urls()):
                event.acceptProposedAction()
                self.setStyleSheet(
                    f"QFrame {{ background: rgba(79,195,247,0.15); border: 2px dashed {Colors.ACCENT}; border-radius: 6px; }}"
                )

    def dragLeaveEvent(self, event):
        self._idle()

    def dropEvent(self, event: QDropEvent):
        self._idle()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()
                 if Path(u.toLocalFile()).suffix.lower() in self._extensions]
        self._import_files(paths)
        event.acceptProposedAction()

    def _import_files(self, paths: list[Path]):
        self._target.mkdir(parents=True, exist_ok=True)
        dropped = []
        for src in paths:
            if src.is_file():
                dest = self._target / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
                dropped.append(dest)
        if dropped:
            self.files_dropped.emit(dropped)
