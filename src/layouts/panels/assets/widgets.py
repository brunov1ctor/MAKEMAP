"""Asset Manager Widgets — MiniSlider, SoundColumn, DropZone."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import ClassVar

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy, QSlider, QToolButton, QFileDialog, QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QUrl, QVariantAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QColor, QConicalGradient
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.styles.tokens import Colors

_SUPPORTED_SND = {".wav", ".mp3", ".ogg", ".flac"}
_SUPPORTED_IMG = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".webm", ".mov"}

_GLOW_STEP_DEG = 6  # avanço do ângulo do glow circulante por tick do timer


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
    _hash_to_color: ClassVar[dict[str, QColor]] = {}

    @staticmethod
    def _color_for_hash(file_hash: str) -> QColor:
        """Cor determinística por grupo: mesmo arquivo = mesma cor sempre,
        arquivos diferentes tendem a cores bem distintas (matiz varia com o hash)."""
        hue = int(file_hash[:8], 16) % 360
        return QColor.fromHsl(hue, 200, 140)

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
    def unregister_all(cls, col: SoundColumn):
        """Remove a column from every hash group — used when its widget is destroyed."""
        for file_hash, cols in list(cls._hash_to_cols.items()):
            if col in cols:
                cols.discard(col)
                cls._refresh_group(file_hash)

    @classmethod
    def _refresh_group(cls, file_hash: str):
        cols = {c for c in cls._hash_to_cols.get(file_hash, set()) if c._sound_hash == file_hash}
        shared = len(cols) > 1
        color = cls._color_for_hash(file_hash) if shared else None
        if shared:
            cls._hash_to_color[file_hash] = color
        else:
            cls._hash_to_color.pop(file_hash, None)
        alive = set()
        for c in cols:
            try:
                c._set_shared_style(shared, color)
                alive.add(c)
            except RuntimeError:
                pass  # underlying widget already destroyed — drop the stale entry
        cls._hash_to_cols[file_hash] = alive

    @classmethod
    def propagate_rename(cls, file_hash: str, new_display: str, source: SoundColumn):
        """Atualiza o nome exibido em todos os peers do mesmo hash."""
        for c in list(cls._hash_to_cols.get(file_hash, set())):
            if c is not source:
                c._apply_display_name(new_display)

    @classmethod
    def highlight_group(cls, file_hash: str, active: bool):
        """Liga/desliga o glow neon circulante em todos os membros do grupo
        (inclusive quem disparou o hover) — só tem efeito em grupos com
        duplicata (>1 coluna registrada sob o mesmo hash)."""
        cols = cls._hash_to_cols.get(file_hash, set())
        if len(cols) < 2:
            return
        for c in list(cols):
            try:
                c._set_group_glow(active)
            except RuntimeError:
                pass


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

    def set_value(self, value: int):
        self._slider.setValue(value)


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
        self._group_color: QColor | None = None
        self._glow_alpha = 0.0
        self._glow_phase = 0.0
        self.setStyleSheet("background: transparent; border: none;")
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.destroyed.connect(lambda: SoundRegistry.unregister_all(self))

        self._glow_anim = QVariantAnimation(self)
        self._glow_anim.setDuration(180)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._glow_anim.valueChanged.connect(self._on_glow_anim)

        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(40)
        self._glow_timer.timeout.connect(self._advance_glow_phase)

        # carrega do banco
        saved_volume = 70
        display_name = ""
        try:
            from src.engines.assets.library import get_shared_db
            db = get_shared_db()
            row = db.execute(
                "SELECT path, volume, display_name FROM asset_sounds WHERE asset_id=? AND prefix=?",
                (asset_id, prefix)
            ).fetchone()
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
        self._clear_btn.setToolTip("Remover som")
        self._clear_btn.setStyleSheet(
            f"QToolButton {{ background: rgba(0,0,0,0.6); border: none; font-size: 6px; "
            f"color: {Colors.TEXT_MUTED}; border-radius: 6px; }}"
            f"QToolButton:hover {{ color: {Colors.ERROR}; }}"
            f"QToolTip {{"
            f"    background-color: {Colors.BG_ELEVATED};"
            f"    color: {Colors.TEXT_PRIMARY};"
            f"    border: 1px solid {Colors.BORDER};"
            f"    border-radius: 8px;"
            f"    padding: 6px 10px;"
            f"    font-size: 11px;"
            f"}}"
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
            f"QToolTip {{"
            f"    background-color: {Colors.BG_ELEVATED};"
            f"    color: {Colors.TEXT_PRIMARY};"
            f"    border: 1px solid {Colors.BORDER};"
            f"    border-radius: 8px;"
            f"    padding: 6px 10px;"
            f"    font-size: 11px;"
            f"}}"
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
            from src.engines.assets.library import get_shared_db
            db = get_shared_db()
            db.execute(
                """INSERT INTO asset_sounds (asset_id, prefix, path, volume, display_name)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(asset_id, prefix) DO UPDATE SET
                       path=excluded.path, volume=excluded.volume, display_name=excluded.display_name""",
                (self._asset_id, self._prefix, path, volume, display_name)
            )
            db.commit()
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
                from src.engines.assets.library import get_shared_db
                db = get_shared_db()
                db.execute(
                    "DELETE FROM asset_sounds WHERE asset_id=? AND prefix=?",
                    (self._asset_id, self._prefix)
                )
                db.commit()
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

    def _set_shared_style(self, shared: bool, color: QColor | None = None):
        """Borda na cor do grupo quando o som é compartilhado com outro asset
        — cada grupo de arquivo idêntico tem sua própria cor (SoundRegistry)."""
        self._group_color = color if shared else None
        if shared and color is not None:
            border = color.toRgb()
            bg = QColor(color)
            self._drop_frame.setStyleSheet(
                f"QFrame {{ background: rgba({bg.red()},{bg.green()},{bg.blue()},20); "
                f"border: 1px solid rgba({border.red()},{border.green()},{border.blue()},230); "
                f"border-radius: 4px; }}"
            )
        else:
            if self._sound_path:
                self._drop_filled()
            else:
                self._drop_idle()

    def _advance_glow_phase(self):
        self._glow_phase = (self._glow_phase + _GLOW_STEP_DEG) % 360
        self.update()

    def _on_glow_anim(self, value):
        self._glow_alpha = value
        self.update()

    def _set_group_glow(self, active: bool):
        """Liga/desliga o glow neon circulante deste membro do grupo —
        chamado pelo SoundRegistry.highlight_group ao passar o mouse sobre
        qualquer coluna do mesmo grupo de som duplicado."""
        if active:
            if not self._glow_timer.isActive():
                self._glow_timer.start()
        else:
            self._glow_timer.stop()
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._glow_alpha)
        self._glow_anim.setEndValue(1.0 if active else 0.0)
        self._glow_anim.start()

    def enterEvent(self, event):
        if self._sound_hash:
            SoundRegistry.highlight_group(self._sound_hash, True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._sound_hash:
            SoundRegistry.highlight_group(self._sound_hash, False)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._glow_alpha <= 0.01 or self._group_color is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._drop_frame.geometry()
        grad = QConicalGradient(rect.center(), self._glow_phase)
        base = QColor(self._group_color)
        for stop, alpha in ((0.0, 0.75), (0.25, 0.05), (0.5, 0.75), (0.75, 0.05), (1.0, 0.75)):
            c = QColor(base)
            c.setAlphaF(alpha * self._glow_alpha)
            grad.setColorAt(stop, c)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 6, 6)
        p.end()

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
