"""Asset Manager Widgets — MiniSlider, SoundColumn, DropZone."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QSlider, QToolButton, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.styles.tokens import Colors

_SUPPORTED_SND = {".wav", ".mp3", ".ogg", ".flac"}
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}


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
    """Coluna de som: drop zone + play + volume slider."""

    def __init__(self, sound_dir: Path, prefix: str = "", parent=None):
        super().__init__(parent)
        self._sound_dir = sound_dir
        self._prefix = prefix
        self._sound_path: str = ""
        self._player: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None
        self.setStyleSheet("background: transparent; border: none;")
        self.setAcceptDrops(True)

        self._saved_volume = 70
        vol_file = sound_dir / f".volume_{prefix}"
        if vol_file.exists():
            try:
                self._saved_volume = int(float(vol_file.read_text().strip()) * 100)
            except (ValueError, OSError):
                pass

        if sound_dir.exists():
            for f in sound_dir.iterdir():
                if (f.is_file() and f.suffix.lower() in _SUPPORTED_SND
                        and f.stem.lower().startswith(prefix)):
                    self._sound_path = str(f)
                    break

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._drop_frame = QFrame()
        self._drop_frame.setFixedSize(42, 42)
        self._drop_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drop_frame.setAcceptDrops(True)
        self._drop_idle()

        drop_lay = QVBoxLayout(self._drop_frame)
        drop_lay.setContentsMargins(2, 2, 2, 2)
        drop_lay.setSpacing(0)
        drop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._drop_icon = QLabel("🔊")
        self._drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        drop_lay.addWidget(self._drop_icon)

        self._drop_label = QLabel("")
        self._drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 5pt; background: transparent; border: none;")
        drop_lay.addWidget(self._drop_label)

        self._clear_btn = QToolButton(self._drop_frame)
        self._clear_btn.setText("✕")
        self._clear_btn.setFixedSize(12, 12)
        self._clear_btn.move(30, 0)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            f"QToolButton {{ background: rgba(0,0,0,0.6); border: none; font-size: 6px; "
            f"color: {Colors.TEXT_MUTED}; border-radius: 6px; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
        )
        self._clear_btn.clicked.connect(self._clear_sound)
        self._clear_btn.hide()

        self._drop_frame.mousePressEvent = self._on_click_drop
        lay.addWidget(self._drop_frame)

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
        lay.addWidget(self._play_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(self._saved_volume)
        self._vol.setMaximumWidth(60)
        self._vol.setStyleSheet(
            f"QSlider {{ background: transparent; }}"
            f"QSlider::groove:horizontal {{ height: 3px; background: rgba(255,255,255,0.1); border-radius: 1px; }}"
            f"QSlider::handle:horizontal {{ width: 8px; height: 8px; margin: -3px 0; "
            f"background: {Colors.TEXT_SECONDARY}; border-radius: 4px; }}"
            f"QSlider::sub-page:horizontal {{ background: rgba(255,255,255,0.2); border-radius: 1px; }}"
        )
        self._vol.valueChanged.connect(self._on_volume_changed)
        lay.addWidget(self._vol, 1)

        if self._sound_path:
            self._set_sound(self._sound_path)

    def _on_volume_changed(self, value: int):
        self._sound_dir.mkdir(parents=True, exist_ok=True)
        vol_file = self._sound_dir / f".volume_{self._prefix}"
        try:
            vol_file.write_text(f"{value / 100.0:.2f}")
        except OSError:
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
        self._sound_path = path
        name = Path(path).stem if path else ""
        if name:
            self._drop_label.setText(name)
            self._drop_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 7pt; background: transparent; border: none;")
            self._clear_btn.show()
            self._drop_filled()
        else:
            self._drop_label.setText("Arraste som aqui")
            self._drop_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 7pt; background: transparent; border: none;")
            self._clear_btn.hide()
            self._drop_idle()

    def _clear_sound(self):
        self._set_sound("")

    def _on_click_drop(self, event):
        exts = ' '.join('*' + e for e in _SUPPORTED_SND)
        file, _ = QFileDialog.getOpenFileName(self, "Selecionar Som", "", f"Sons ({exts})")
        if file:
            dest = self._import_sound(Path(file))
            self._set_sound(str(dest))

    def _import_sound(self, src: Path) -> Path:
        self._sound_dir.mkdir(parents=True, exist_ok=True)
        name = src.name
        if self._prefix and not name.lower().startswith(self._prefix):
            name = f"{self._prefix}_{name}"
        dest = self._sound_dir / name
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
        self._output = QAudioOutput(self)
        self._output.setVolume(self._vol.value() / 100.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._output)
        self._player.setSource(QUrl.fromLocalFile(self._sound_path))
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
