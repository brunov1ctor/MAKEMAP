"""LiveSplitter — drop-in QSplitter replacement whose handle reacts to the
mouse instead of just swapping the cursor icon. Every panel in the app
(dungeons, items, mobs, npcs, ...) builds a plain QSplitter with the same
copy-pasted `"QSplitter::handle { background: transparent; }"` — the only
hover feedback was the resize cursor Qt already gives for free. This adds a
real highlight, plus a soft pulsing glow while hovered, same
QVariantAnimation + QTimer pattern already used for the sound-duplicate glow
in src/layouts/panels/assets/widgets.py's SoundColumn.
"""

from __future__ import annotations

import math

from PySide6.QtWidgets import QSplitter, QSplitterHandle
from PySide6.QtCore import Qt, QRectF, QVariantAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPainter, QColor

from src.styles.tokens import Colors

_PULSE_STEP = 0.12  # rad por tick do timer — velocidade do pulso
_BAR_THICKNESS = 4  # espessura da barra pintada, mais fina que o handle inteiro (área de arrasto continua com o setHandleWidth() de cada painel)


class LiveSplitterHandle(QSplitterHandle):
    """Barra fina sempre visível (linha translúcida) que ganha um brilho
    pulsante na cor de destaque enquanto o mouse está em cima — some com
    a mesma animação de fade ao tirar o mouse."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self._glow_alpha = 0.0
        self._pulse_phase = 0.0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance_pulse)

    def _on_anim(self, value):
        self._glow_alpha = value
        self.update()

    def _advance_pulse(self):
        self._pulse_phase = (self._pulse_phase + _PULSE_STEP) % (2 * math.pi)
        self.update()

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._glow_alpha)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._glow_alpha)
        self._anim.setEndValue(0.0)
        self._anim.start()
        self._timer.stop()
        super().leaveEvent(event)

    def paintEvent(self, event):
        # Sem hover, sem pintura nenhuma — nada de traço/fundo permanente
        # (era isso que "background: transparent" já dava antes). Só
        # aparece algo enquanto _glow_alpha > 0, ou seja, durante o hover
        # e o fade de saída logo depois dele.
        if self._glow_alpha <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Barra fina e arredondada (tipo pílula), centrada na área de
        # arrasto — não a preenche inteira, só destaca visualmente; a
        # largura/altura de arrasto real continua sendo o setHandleWidth()
        # de cada painel.
        full = QRectF(self.rect())
        if self.orientation() == Qt.Orientation.Horizontal:
            x = full.center().x() - _BAR_THICKNESS / 2
            rect = QRectF(x, full.top(), _BAR_THICKNESS, full.height())
        else:
            y = full.center().y() - _BAR_THICKNESS / 2
            rect = QRectF(full.left(), y, full.width(), _BAR_THICKNESS)
        # Pulso senoidal (0.55–1.0) modulado pelo fade de entrada/saída.
        pulse = 0.55 + 0.45 * math.sin(self._pulse_phase)
        color = QColor(Colors.ACCENT)
        color.setAlphaF(min(1.0, 0.30 + 0.70 * pulse) * self._glow_alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(rect, _BAR_THICKNESS / 2, _BAR_THICKNESS / 2)
        p.end()


class LiveSplitter(QSplitter):
    """QSplitter cujo `createHandle()` devolve um LiveSplitterHandle —
    mesma API/uso de QSplitter normal, só a pintura do divisor muda."""

    def createHandle(self):
        return LiveSplitterHandle(self.orientation(), self)
