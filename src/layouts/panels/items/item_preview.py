"""ItemPreview — the right column of the Itens row: a big PRÉVIA image on
top and an INFORMAÇÕES RÁPIDAS stat readout below.

Purely presentational — update(record) re-renders from whatever the editor
last saved; DPS is derived (Ataque × Vel. de Ataque) exactly like the
reference (35 × 1,28 ≈ 45).
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from src.styles.tokens import Colors
from src.layouts.panels.items.constants import (
    panel_frame_style, sub_header, category_display,
)


class _DropImageLabel(QLabel):
    """The big PRÉVIA image area — click does nothing, but an image file
    dragged onto it from Explorer is accepted and emitted as image_dropped."""

    image_dropped = Signal(str)
    _ACCEPTED = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    def _accepted_path(self, mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(self._ACCEPTED):
                return path
        return None

    def dragEnterEvent(self, event):
        if self._accepted_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._accepted_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.image_dropped.emit(path)
        else:
            event.ignore()


def _fmt(value: float, decimals: int = 0, suffix: str = "") -> str:
    """PT-BR-ish number formatting (comma decimal) to match the reference."""
    if decimals:
        text = f"{value:.{decimals}f}".replace(".", ",")
    else:
        text = f"{value:g}" if value != int(value) else str(int(value))
    return f"{text}{suffix}"


class ItemPreview(QWidget):
    image_dropped = Signal(str)  # bubbled up from the PRÉVIA drop area

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # ── PRÉVIA ──
        preview_frame = QFrame()
        preview_frame.setObjectName("subpanel")
        preview_frame.setStyleSheet(panel_frame_style())
        preview_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        pv = QVBoxLayout(preview_frame)
        pv.setContentsMargins(12, 10, 12, 12)
        pv.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(sub_header("Prévia"))
        head.addStretch()
        self._import_btn = QPushButton("Importar")
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.05); color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 5px; padding: 3px 10px; font-size: 9px; }}
            QPushButton:hover {{ background: {Colors.PANEL_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
        """)
        head.addWidget(self._import_btn)
        pv.addLayout(head)

        self._image = _DropImageLabel("🗡")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Um piso baixo (não 150) — esse rótulo é o maior responsável pela
        # altura mínima da linha Itens (~352px). Com o divisor vertical
        # agora colapsável, um piso alto faz o arraste "saltar" de um bom
        # pedaço da tela direto pro colapso total assim que esbarra nele,
        # em vez de encolher suavemente até quase zero.
        self._image.setMinimumHeight(40)
        self._image.setToolTip("Arraste uma imagem aqui")
        self._image.setStyleSheet(
            f"font-size: 72px; background: qradialgradient(cx:0.5, cy:0.4, radius:0.7, "
            f"stop:0 rgba(79,195,247,0.10), stop:1 transparent); border: none; border-radius: 8px;"
        )
        self._image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image.image_dropped.connect(self.image_dropped.emit)
        pv.addWidget(self._image, 1)
        outer.addWidget(preview_frame, 3)

        # ── INFORMAÇÕES RÁPIDAS ──
        info_frame = QFrame()
        info_frame.setObjectName("subpanel")
        info_frame.setStyleSheet(panel_frame_style())
        info_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        iv = QVBoxLayout(info_frame)
        iv.setContentsMargins(12, 10, 12, 10)
        iv.setSpacing(4)
        iv.addWidget(sub_header("Informações Rápidas"))

        self._rows: dict[str, QLabel] = {}
        for key, label in [
            ("dps", "DPS"), ("attack", "Ataque"), ("atk_speed", "Vel. de Ataque"),
            ("crit", "Crítico"), ("range", "Alcance"),
            ("dmg_type", "Tipo de Dano"), ("element", "Elemento"),
        ]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 1, 0, 1)
            name = QLabel(label)
            name.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
            row.addWidget(name)
            row.addStretch()
            value = QLabel("—")
            value.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 10px; font-weight: bold; background: transparent; border: none;")
            row.addWidget(value)
            self._rows[key] = value
            iv.addLayout(row)
        outer.addWidget(info_frame, 2)

        self.update(None)

    @property
    def import_button(self) -> QPushButton:
        return self._import_btn

    def update(self, record: dict | None):
        if not record:
            self._image.setText("🗡")
            self._image.setPixmap(QPixmap())
            for lbl in self._rows.values():
                lbl.setText("—")
            return

        image_path = record.get("image_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            self._image.setPixmap(pixmap.scaled(
                220, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            self._image.setPixmap(QPixmap())
            self._image.setText(record.get("icon") or "🗡")

        stats = self._parse_stats(record.get("stats"))
        attack = float(stats.get("attack", 0))
        atk_speed = float(stats.get("atk_speed", 1.0))
        dps = attack * atk_speed
        self._rows["dps"].setText(_fmt(dps, 1))
        self._rows["attack"].setText(_fmt(attack))
        self._rows["atk_speed"].setText(_fmt(atk_speed, 2))
        self._rows["crit"].setText(_fmt(float(stats.get("crit", 0)), 0, "%"))
        self._rows["range"].setText(_fmt(float(stats.get("range", 0)), 1, "m"))
        self._rows["dmg_type"].setText(stats.get("dmg_type", "—") or "—")
        self._rows["element"].setText(stats.get("element", "Nenhum") or "Nenhum")

    @staticmethod
    def _parse_stats(raw) -> dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
