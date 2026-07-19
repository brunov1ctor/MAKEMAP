"""Region Card — single zone entry with name, star rating, locate, and delete.

Mirrors TerrainCard (terrain/terrain_card.py) closely, minus drag-reorder
(not needed here), plus a 5-star rating row.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QStackedWidget, QLineEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from src.styles.tokens import Colors


class RegionCard(QFrame):
    """A single region (zone) entry card with name, star rating, and delete."""

    selected = Signal(str)
    deleted = Signal(str)
    renamed = Signal(str, str)
    locate_requested = Signal(str)
    stars_changed = Signal(str, int)

    def __init__(self, region_id: str, name: str, color: QColor, stars: int = 0, parent=None):
        super().__init__(parent)
        self.region_id = region_id
        self._selected = False
        self._stars = stars
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._build_style(False))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Color swatch (category color)
        swatch = QLabel()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"""
            background: {color.name()}; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2);
        """)
        layout.addWidget(swatch)

        # Name (label + edit stacked)
        self._name_stack = QStackedWidget()
        self._name_stack.setFixedHeight(22)

        self._name_label = QLabel(name)
        self._name_label.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY}; font-size: 11px;
            background: transparent; border: none;
        """)

        self._name_edit = QLineEdit(name)
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {Colors.TEXT_PRIMARY}; font-size: 11px;
                background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT};
                border-radius: 3px; padding: 0 4px;
            }}
        """)
        self._name_edit.returnPressed.connect(self._finish_rename)
        self._name_edit.editingFinished.connect(self._finish_rename)

        self._name_stack.addWidget(self._name_label)
        self._name_stack.addWidget(self._name_edit)
        self._name_stack.setCurrentIndex(0)
        layout.addWidget(self._name_stack, 1)

        # Star rating row
        self._star_buttons: list[QToolButton] = []
        stars_row = QHBoxLayout()
        stars_row.setSpacing(0)
        for i in range(1, 6):
            btn = QToolButton()
            btn.setFixedSize(16, 16)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none; background: transparent; font-size: 11px;
                    color: {Colors.TEXT_MUTED}; padding: 0;
                }}
                QToolButton:hover {{ color: {Colors.ACCENT}; }}
            """)
            btn.clicked.connect(lambda checked=False, n=i: self._on_star_clicked(n))
            stars_row.addWidget(btn)
            self._star_buttons.append(btn)
        layout.addLayout(stars_row)
        self._refresh_stars()

        # Locate button
        locate_btn = QToolButton()
        locate_btn.setText("📍")
        locate_btn.setFixedSize(22, 22)
        locate_btn.setToolTip("Localizar no mapa")
        locate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        locate_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_SECONDARY}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.ACCENT}; }}
        """)
        locate_btn.clicked.connect(lambda: self.locate_requested.emit(self.region_id))
        layout.addWidget(locate_btn)

        # Rename button
        rename_btn = QToolButton()
        rename_btn.setText("✎")
        rename_btn.setFixedSize(22, 22)
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 12px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(255,255,255,0.08); color: {Colors.TEXT_PRIMARY}; }}
        """)
        rename_btn.clicked.connect(self._start_rename)
        layout.addWidget(rename_btn)

        # Delete button
        del_btn = QToolButton()
        del_btn.setText("🗑")
        del_btn.setFixedSize(22, 22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QToolButton {{
                border: none; border-radius: 4px; font-size: 11px;
                color: {Colors.TEXT_MUTED}; background: transparent;
            }}
            QToolButton:hover {{ background: rgba(239,83,80,0.2); color: {Colors.ERROR}; }}
        """)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.region_id))
        layout.addWidget(del_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.region_id)
        super().mousePressEvent(event)

    def set_selected(self, sel: bool):
        self._selected = sel
        self.setStyleSheet(self._build_style(sel))

    def _build_style(self, sel: bool) -> str:
        if sel:
            return f"""
                QFrame {{
                    background: {Colors.ACCENT_DIM}; border: 1px solid {Colors.ACCENT};
                    border-radius: 6px;
                }}
            """
        return f"""
            QFrame {{
                background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE};
                border-radius: 6px;
            }}
            QFrame:hover {{ background: rgba(255,255,255,0.08); }}
        """

    def _start_rename(self):
        self._name_edit.setText(self._name_label.text())
        self._name_stack.setCurrentIndex(1)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _finish_rename(self):
        if self._name_stack.currentIndex() != 1:
            return
        new_name = self._name_edit.text().strip()
        if new_name and new_name != self._name_label.text():
            self._name_label.setText(new_name)
            self.renamed.emit(self.region_id, new_name)
        self._name_stack.setCurrentIndex(0)

    def _on_star_clicked(self, n: int):
        self.set_stars(n)
        self.stars_changed.emit(self.region_id, n)

    def set_stars(self, stars: int):
        self._stars = max(0, min(5, stars))
        self._refresh_stars()

    def _refresh_stars(self):
        for i, btn in enumerate(self._star_buttons, start=1):
            filled = i <= self._stars
            btn.setText("★" if filled else "☆")
            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none; background: transparent; font-size: 11px;
                    color: {Colors.ACCENT if filled else Colors.TEXT_MUTED}; padding: 0;
                }}
                QToolButton:hover {{ color: {Colors.ACCENT}; }}
            """)

    @property
    def name(self) -> str:
        return self._name_label.text()

    @property
    def stars(self) -> int:
        return self._stars
