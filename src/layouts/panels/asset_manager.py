"""Asset & Sound Manager — layout tabular estilo mockup.

Cada categoria é colapsável. Cada asset mostra numa única linha:
[thumb] [nome + tamanho] [brilho/contraste] [brush sound + vol] [ambient sound + vol] [🗑]
"""

from __future__ import annotations

import shutil
import struct
import wave
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QSlider, QToolButton,
    QFileDialog, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QSize, QUrl
from PySide6.QtGui import QColor, QPixmap, QDragEnterEvent, QDropEvent, QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.styles.tokens import Colors
from src.services.asset_adjustments import apply_brightness_contrast

_LIB = Path(__file__).resolve().parents[3] / "library"
_ASSETS_DIR = _LIB / "assets"
_SOUNDS_DIR = _LIB / "sounds"
_BG_DIR = _LIB / "backgrounds"

_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
_SUPPORTED_SND = {".wav", ".mp3", ".ogg", ".flac"}

_CARD_BG = "rgba(255, 255, 255, 0.03)"
_CARD_BORDER = "rgba(255, 255, 255, 0.08)"
_DROP_BG = "rgba(79, 195, 247, 0.06)"
_DROP_BORDER = "rgba(79, 195, 247, 0.35)"

MAX_SOUND_DURATION_S = 30
FADE_DURATION_S = 1.5


# ─── Audio Processing ────────────────────────────────────────────────────────

def _process_sound_file(src: Path, dest: Path):
    """Trim to 30s or loop short sounds with crossfade to fill 30s."""
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        _process_with_ffmpeg(src, dest)
    except (FileNotFoundError, OSError, Exception):
        if src.suffix.lower() == ".wav":
            _process_wav_pure(src, dest)
        else:
            shutil.copy2(src, dest)


def _process_with_ffmpeg(src: Path, dest: Path):
    import subprocess
    tmp_wav = dest.with_suffix(".tmp.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2", str(tmp_wav)],
        capture_output=True, check=True,
    )
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(tmp_wav)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())

    if duration >= MAX_SOUND_DURATION_S:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_wav), "-t", str(MAX_SOUND_DURATION_S),
             "-af", f"afade=t=out:st={MAX_SOUND_DURATION_S - FADE_DURATION_S}:d={FADE_DURATION_S}",
             str(dest)], capture_output=True, check=True)
    else:
        loops = int(MAX_SOUND_DURATION_S / duration) + 1
        subprocess.run(
            ["ffmpeg", "-y", "-stream_loop", str(loops - 1), "-i", str(tmp_wav),
             "-t", str(MAX_SOUND_DURATION_S),
             "-af", f"afade=t=out:st={MAX_SOUND_DURATION_S - FADE_DURATION_S}:d={FADE_DURATION_S}",
             str(dest)], capture_output=True, check=True)
    tmp_wav.unlink(missing_ok=True)


def _process_wav_pure(src: Path, dest: Path):
    """Pure Python wav: trim/loop to 30s with crossfade."""
    with wave.open(str(src), 'rb') as wf:
        n_ch = wf.getnchannels()
        sw = wf.getsampwidth()
        fr = wf.getframerate()
        nf = wf.getnframes()
        raw = wf.readframes(nf)

    if sw != 2:
        shutil.copy2(src, dest)
        return

    samples = list(struct.unpack(f"<{nf * n_ch}h", raw))
    duration = nf / fr
    target_frames = int(MAX_SOUND_DURATION_S * fr)
    fade_frames = int(FADE_DURATION_S * fr)

    if duration >= MAX_SOUND_DURATION_S:
        samples = samples[:target_frames * n_ch]
        fs = (target_frames - fade_frames) * n_ch
        for i in range(fs, len(samples)):
            samples[i] = int(samples[i] * (1.0 - (i - fs) / (fade_frames * n_ch)))
    else:
        src_s = list(samples)
        result = list(src_s)
        cf_len = fade_frames * n_ch
        while len(result) < target_frames * n_ch:
            if cf_len > len(src_s):
                cf_len = len(src_s) // 2
            start = len(result) - cf_len
            for i in range(cf_len):
                p = i / cf_len
                result[start + i] = int(result[start + i] * (1.0 - p) + src_s[i] * p)
            result.extend(src_s[cf_len:])
        samples = result[:target_frames * n_ch]
        fs = (target_frames - fade_frames) * n_ch
        for i in range(fs, len(samples)):
            samples[i] = int(samples[i] * (1.0 - (i - fs) / (fade_frames * n_ch)))

    samples = [max(-32768, min(32767, s)) for s in samples]
    packed = struct.pack(f"<{len(samples)}h", *samples)
    with wave.open(str(dest), 'wb') as wf:
        wf.setnchannels(n_ch)
        wf.setsampwidth(sw)
        wf.setframerate(fr)
        wf.writeframes(packed)


# ─── Mini Slider ─────────────────────────────────────────────────────────────

class _MiniSlider(QWidget):
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


# ─── Sound Column (vertical: combo + icon/play + volume) ─────────────────────

class _SoundColumn(QWidget):
    """Coluna de som: [drop zone / nome do som] [🎧 play] [volume slider].
    Aceita drag & drop de arquivos de som para associar ao asset.
    """

    def __init__(self, sound_dir: Path, prefix: str = "", parent=None):
        super().__init__(parent)
        self._sound_dir = sound_dir
        self._prefix = prefix  # e.g. "paint" or "ambient"
        self._sound_path: str = ""
        self._player: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None
        self.setStyleSheet("background: transparent; border: none;")
        self.setAcceptDrops(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Drop area (quadrado com ícone de som)
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

        # Botão remover som (canto)
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
        self._vol.setValue(70)
        self._vol.setMaximumWidth(60)
        self._vol.setStyleSheet(
            f"QSlider {{ background: transparent; }}"
            f"QSlider::groove:horizontal {{ height: 3px; background: rgba(255,255,255,0.1); border-radius: 1px; }}"
            f"QSlider::handle:horizontal {{ width: 8px; height: 8px; margin: -3px 0; "
            f"background: {Colors.TEXT_SECONDARY}; border-radius: 4px; }}"
            f"QSlider::sub-page:horizontal {{ background: rgba(255,255,255,0.2); border-radius: 1px; }}"
        )
        lay.addWidget(self._vol, 1)

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
        """Define o som associado."""
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
        """Clique abre file dialog para selecionar som."""
        exts = ' '.join('*' + e for e in _SUPPORTED_SND)
        file, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Som", "", f"Sons ({exts})"
        )
        if file:
            dest = self._import_sound(Path(file))
            self._set_sound(str(dest))

    def _import_sound(self, src: Path) -> Path:
        """Copia som para a pasta da library com prefixo correto e retorna o destino."""
        self._sound_dir.mkdir(parents=True, exist_ok=True)
        # Add prefix if needed so BrushSoundLayer can find it
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
        return {
            "sound": self._sound_path,
            "volume": self._vol.value() / 100.0,
        }


# ─── Asset Row Card ──────────────────────────────────────────────────────────

class AssetRowCard(QFrame):
    """Card de um asset: linha dividida em 3 partes iguais.
    [1/3: thumb+nome+meta+brilho/contraste] | [1/3: brush sound] | [1/3: ambient sound] [🗑]
    """

    removed = Signal(str)
    settings_changed = Signal(str, int, int)  # (asset_path, brightness, contrast)

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

        # Name row: name label + rename button + edit field (same row)
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

        self._brightness = _MiniSlider("Brilho", -100, 100, 0)
        self._brightness.value_changed.connect(self._update_preview)
        info.addWidget(self._brightness)
        self._contrast = _MiniSlider("Contraste", -100, 100, 0)
        self._contrast.value_changed.connect(self._update_preview)
        info.addWidget(self._contrast)

        col1.addLayout(info, 1)
        row.addLayout(col1, 1)

        # ═══ 1/3: Brush Sound ═══
        col2 = QHBoxLayout()
        col2.setContentsMargins(0, 0, 0, 0)
        col2.setSpacing(0)
        col2.addStretch()
        # Save into brush/<category>/ with "paint_" prefix
        brush_dir = _SOUNDS_DIR / "brush" / category.lower().replace(" ", "_")
        self._brush_sound = _SoundColumn(brush_dir, prefix="paint")
        col2.addWidget(self._brush_sound)
        col2.addStretch()
        row.addLayout(col2, 1)

        # ═══ 1/3: Ambient Sound ═══
        col3 = QHBoxLayout()
        col3.setContentsMargins(0, 0, 0, 0)
        col3.setSpacing(0)
        col3.addStretch()
        # Save into brush/<category>/ with "ambient_" prefix
        ambient_dir = _SOUNDS_DIR / "brush" / category.lower().replace(" ", "_")
        self._ambient_sound = _SoundColumn(ambient_dir, prefix="ambient")
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
        b = self._brightness.value()
        c = self._contrast.value()
        # Usar thumb pequeno para preview rápido
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


# ─── Drop Zone ───────────────────────────────────────────────────────────────

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
            f"QFrame {{ background: {_DROP_BG}; border: 1px dashed {_DROP_BORDER}; border-radius: 6px; }}"
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


# ─── Category Section (collapsible table row) ────────────────────────────────

class CategorySection(QWidget):
    """Seção colapsável para uma categoria — header em tabela + cards dos assets."""

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

        # ── Header row ──
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

        # 1/3: arrow + icon + title + rename btn + count
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

        # 1/3: Brush header
        self._brush_hdr = QLabel("🖌 Brush")
        self._brush_hdr.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._brush_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brush_hdr.hide()
        h_lay.addWidget(self._brush_hdr, 1)

        # 1/3: Sounds header
        self._ambient_hdr = QLabel("🔊 Sounds")
        self._ambient_hdr.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 9pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._ambient_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ambient_hdr.hide()
        h_lay.addWidget(self._ambient_hdr, 1)

        main.addWidget(self._header)

        # ── Content ──
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

        # Drop zone
        drop = DropZone(self._folder, _SUPPORTED_IMG)
        drop.files_dropped.connect(self._on_dropped)
        self._content_lay.addWidget(drop)

    def _toggle_rename(self):
        """Toggle rename: first click edits, second click saves."""
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


# ─── Main Manager ────────────────────────────────────────────────────────────

class AssetSoundManager(QWidget):
    """Gerencia TODA a library — layout tabular com categorias colapsáveis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from src.services.asset_adjustments import AssetAdjustmentsService
        # Use singleton service
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

        # ── Title bar ──
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

        # ── Categories ──
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

        # ── Backgrounds ──
        bg_title = QFrame()
        bg_title.setFixedHeight(36)
        bg_title.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.03); border: none; "
            f"border-bottom: 1px solid {Colors.BORDER_SUBTLE}; }}"
        )
        bg_lay = QHBoxLayout(bg_title)
        bg_lay.setContentsMargins(12, 0, 12, 0)
        bg_lay.setSpacing(8)
        bg_lbl = QLabel("🖼 BACKGROUNDS")
        bg_lbl.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11pt; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        bg_lay.addWidget(bg_lbl)
        bg_lay.addStretch()
        main.addWidget(bg_title)

        bg_categories = [
            ("abstract", "🎨", "Abstract"),
            ("mystics", "🔮", "Mystics"),
            ("nature", "🌿", "Nature"),
            ("space", "🌌", "Space"),
            ("terrain", "🏜", "Terrain"),
        ]

        for folder_name, icon, label in bg_categories:
            section = CategorySection(_BG_DIR / folder_name, icon, label)
            main.addWidget(section)

        # Update total count
        total = sum(
            1 for f in _ASSETS_DIR.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_IMG
        )
        self._total_lbl.setText(f"({total})")

        main.addStretch()
