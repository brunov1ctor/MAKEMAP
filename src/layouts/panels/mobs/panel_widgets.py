"""Standalone widget classes used by MobsPanel — none read/write MobsPanel
internals, they're only instantiated and wired via signals by it, so they
live here instead of inline in panel.py.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget, QMenu, QFileDialog
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from src.styles.tokens import Colors


class _InlineNameEdit(QLineEdit):
    """Plain text field used to create a new category inline — emits
    `confirmed` on Enter and `cancelled` on Escape or on losing focus
    without having confirmed, instead of popping a separate QInputDialog
    (its own native top-level window, which read as "opening outside the
    app")."""

    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._confirmed_flag = False
        self.returnPressed.connect(self._on_return)

    def _on_return(self):
        self._confirmed_flag = True
        self.confirmed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self._confirmed_flag:
            self.cancelled.emit()
        self._confirmed_flag = False


class _SidebarRow(QFrame):
    clicked = Signal(str)
    rename_confirmed = Signal(str, str)  # key, new_name — only reachable via the ⋮ menu (show_menu=True)
    delete_requested = Signal(str)  # key — only reachable via the ⋮ menu (show_menu=True)

    def __init__(self, key: str, icon: str, label: str, parent=None, show_menu: bool = False):
        super().__init__(parent)
        self.key = key
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(8)
        # WA_TransparentForMouseEvents on every child label — these three
        # cover almost the whole row, so without it most clicks would land
        # on a label instead of the row itself. Qt's default propagation
        # (an ignored mouse event climbing to the parent) should already
        # cover this, but guaranteeing it directly removes any doubt about
        # whether that propagation is actually happening in a given
        # Qt build/platform — same reasoning as the old _FolderCard had.
        icon_lbl = QLabel(icon)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        icon_lbl.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        lay.addWidget(icon_lbl)
        self._label = QLabel(label)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(self._label, 1)
        self._rename_edit: QLineEdit | None = None  # lazily created — see begin_rename()
        self._count = QLabel("0")
        self._count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._count.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        lay.addWidget(self._count)

        # The ⋮ menu (Renomear/Excluir) is opt-in — only real category
        # folders get one; the pinned smart filters (Todos/Favoritos)
        # aren't user-editable, so they're built with show_menu left False.
        if show_menu:
            menu_btn = QToolButton()
            menu_btn.setText("⋮")
            menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu_btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 12px; padding: 0 4px; }}
                QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
                QToolButton::menu-indicator {{ image: none; width: 0; }}
            """)
            menu = QMenu(menu_btn)
            menu.setStyleSheet(f"""
                QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; }}
                QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
            """)
            menu.addAction("✏ Renomear", self.begin_rename)
            menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self.key))
            menu_btn.setMenu(menu)
            lay.addWidget(menu_btn)

        self._refresh_style()

    def set_count(self, n: int):
        self._count.setText(str(n))

    def set_selected(self, sel: bool):
        self._selected = sel
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet(f"QFrame {{ background: {Colors.ACCENT_DIM}; border-radius: 6px; }}")
            self._label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        else:
            self.setStyleSheet("QFrame { background: transparent; border-radius: 6px; }"
                                "QFrame:hover { background: rgba(255,255,255,0.06); }")
            self._label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")

    def begin_rename(self):
        """Swaps the label for an inline text field pre-filled with the
        current name, right in place — same "no separate window" idea as
        creating a category (see _InlineNameEdit)."""
        if self._rename_edit is None:
            self._rename_edit = _InlineNameEdit(self)
            self._rename_edit.setStyleSheet(f"""
                QLineEdit {{ background: rgba(255,255,255,0.08); border: 1px solid {Colors.ACCENT};
                    border-radius: 4px; padding: 0 4px; color: {Colors.TEXT_PRIMARY}; font-size: 11px; }}
            """)
            self._rename_edit.confirmed.connect(self._on_rename_confirmed)
            self._rename_edit.cancelled.connect(self._on_rename_cancelled)
            self.layout().insertWidget(1, self._rename_edit, 1)  # same slot self._label sits in (index 1, after the icon)
            self._rename_edit.setVisible(False)
        self._rename_edit.setText(self._label.text())
        self._label.setVisible(False)
        self._rename_edit.setVisible(True)
        self._rename_edit.setFocus()
        self._rename_edit.selectAll()

    def _on_rename_confirmed(self):
        new_name = self._rename_edit.text().strip()
        self._rename_edit.setVisible(False)
        self._label.setVisible(True)
        if new_name and new_name != self._label.text():
            self._label.setText(new_name)  # optimistic — MobsPanel's own refresh follows right behind
            self.rename_confirmed.emit(self.key, new_name)

    def _on_rename_cancelled(self):
        self._rename_edit.setVisible(False)
        self._label.setVisible(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class _DropZone(QFrame):
    """Big dashed-border area that accepts a dragged-in JSON/CSV/Excel
    file (or a plain click, opening the same multi-format file picker as
    a fallback for anyone who can't drag-and-drop) — replaces the old
    file-dialog-only Importar flow with something that occupies the right
    panel directly, per the reference behavior requested."""

    file_chosen = Signal(str)  # local file path, either dropped or picked

    _ACCEPTED_SUFFIXES = (".json", ".csv", ".xlsx")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.02); border: 2px dashed {Colors.BORDER_SUBTLE}; border-radius: 10px; }}
        """)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        icon = QLabel("📥")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 40px; background: transparent; border: none;")
        lay.addWidget(icon)
        hint = QLabel("Arraste um arquivo aqui\n(JSON, CSV ou Excel)")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(hint)
        sub = QLabel("ou clique para escolher um arquivo")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; background: transparent; border: none;")
        lay.addWidget(sub)

    def _first_accepted_path(self, mime_data) -> str | None:
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(self._ACCEPTED_SUFFIXES):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and self._first_accepted_path(event.mimeData()):
            event.acceptProposedAction()
            self.setStyleSheet(f"""
                QFrame {{ background: rgba(255,255,255,0.05); border: 2px dashed {Colors.ACCENT}; border-radius: 10px; }}
            """)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.02); border: 2px dashed {Colors.BORDER_SUBTLE}; border-radius: 10px; }}
        """)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        path = self._first_accepted_path(event.mimeData())
        self.dragLeaveEvent(event)  # restore the idle style regardless of outcome
        if path:
            event.acceptProposedAction()
            self.file_chosen.emit(path)
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path, _selected = QFileDialog.getOpenFileName(
                self, "Importar Mobs", "", "Todos os suportados (*.json *.csv *.xlsx);;JSON (*.json);;CSV (*.csv);;Excel (*.xlsx)",
            )
            if path:
                self.file_chosen.emit(path)
        super().mousePressEvent(event)


class _SummaryCard(QFrame):
    """"Resumo Rápido" card — hides its legend (keeping just the donut)
    once there isn't enough height to show both without the legend's
    fixed-size rows overlapping the donut, instead of forcing a floor
    size to guarantee they always fit.

    minimumSizeHint/sizeHint are deliberately capped to "just the donut,
    no legend" REGARDLESS of whether the legend is currently visible —
    letting them grow to the legend's real footprint (which a plain QFrame
    would do automatically) makes this card's own minimum size balloon to
    ~220px, which then inflates _left_container's minimum, then the
    splitter's, then this whole MobsPanel's effective minimum size. Once
    that chain exists, the ENTIRE panel (and the window containing it)
    can't shrink below whatever height the legend needs on its own — on a
    smaller monitor that either refuses to shrink the window at all, or
    forces Qt to render everything below its declared minimum, which is
    exactly where the donut/legend overlap corruption came from in the
    first place. Capping the hint breaks that chain: the card (and
    everything above it) can always shrink freely, and resizeEvent below
    independently decides whether there's enough *actual* room to also
    show the legend."""

    # Tuned to roughly "RESUMO RÁPIDO" label + donut (96px) + margins/
    # spacing alone, with no legend — below this the legend would have
    # nowhere to go but overlap the donut, so it hides instead.
    _LEGEND_MIN_CARD_H = 170
    _COLLAPSED_SIZE = QSize(150, 140)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._legend_container: QWidget | None = None

    def set_legend_container(self, widget: QWidget):
        self._legend_container = widget

    def minimumSizeHint(self):
        return self._COLLAPSED_SIZE

    def sizeHint(self):
        return self._COLLAPSED_SIZE

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._legend_container is not None:
            self._legend_container.setVisible(self.height() >= self._LEGEND_MIN_CARD_H)
