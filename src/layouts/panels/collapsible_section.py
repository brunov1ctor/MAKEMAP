"""CollapsibleSection — header (arrow + title) + content area that
show/hides on click. Shared by RegionEditPanel and TerrainSettingsPanel so
both get the same "grow with content" behavior: emits `content_changed`
on every expand/collapse so the owning panel can re-measure and resize
(see PanelManager._content_height / the panels' own content_height()).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer

from src.styles.tokens import Colors


class _SectionHeader(QFrame):
    """Clickable header row — a real subclass with mousePressEvent
    overridden as an actual method, not a lambda monkeypatched onto a
    plain QFrame() instance. Qt's virtual-call dispatch only reliably
    routes through Python for classes Python itself subclassed; assigning
    to `.mousePressEvent` on a stock QFrame() gave no such guarantee."""

    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class CollapsibleSection(QFrame):
    """Header (arrow + title) + content area that show/hides on click."""

    content_changed = Signal()  # emitted on expand/collapse

    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._expanded = expanded

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(4)

        header = _SectionHeader()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border-radius: 4px; }}
            QFrame:hover {{ background: rgba(255,255,255,0.06); }}
        """)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(8, 5, 8, 5)
        h_lay.setSpacing(6)

        self._arrow = QLabel("▼" if expanded else "▶")
        self._arrow.setFixedWidth(10)
        self._arrow.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 8px; background: transparent; border: none;")
        h_lay.addWidget(self._arrow)

        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(f"""
            color: {Colors.ACCENT}; font-size: 10px; font-weight: bold;
            background: transparent; border: none;
        """)
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()
        header.clicked.connect(self._toggle)
        main.addWidget(header)

        self._content = QFrame()
        self._content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(4, 2, 4, 4)
        self.content_layout.setSpacing(8)
        self._content.setVisible(expanded)
        main.addWidget(self._content)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")
        # setVisible() invalidates ancestor layouts by POSTING a deferred
        # LayoutRequest event rather than recomputing synchronously — an
        # owning panel that re-measures/resizes immediately (same call
        # stack) reads a stale sizeHint() from before this toggle, one
        # step behind. Deferring the emit to the next event-loop turn lets
        # that pending layout pass land first, so the resize sees the
        # correct post-toggle size (most visible after several toggles:
        # collapsing the last still-expanded section stops shrinking the
        # panel back down).
        QTimer.singleShot(0, self.content_changed.emit)

    def set_expanded(self, expanded: bool):
        if expanded == self._expanded:
            return
        self._toggle()
