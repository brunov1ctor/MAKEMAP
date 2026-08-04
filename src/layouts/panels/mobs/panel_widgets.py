"""Standalone widget classes used by MobsPanel — none read/write MobsPanel
internals, they're only instantiated and wired via signals by it, so they
live here instead of inline in panel.py.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget, QMenu
from PySide6.QtCore import Qt, Signal, QSize, QRectF, QPoint, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDrag, QPixmap, QPainter, QPainterPath

from src.styles.tokens import Colors


def _rounded_thumbnail(path: str, size: int) -> QPixmap | None:
    """Square, rounded-corner crop of `path` for a _SidebarRow's icon slot
    (used instead of the emoji glyph once a category has an image_path) —
    same cover-fit + rounded-clip idea as _DropImageButton/MobCard's
    thumbnail, just baked into a flat QPixmap since QLabel has no
    paintEvent hook of its own to draw into."""
    src = QPixmap(path)
    if src.isNull():
        return None
    scaled = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - size) // 2)
    y = max(0, (scaled.height() - size) // 2)
    cropped = scaled.copy(x, y, size, size)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path_clip = QPainterPath()
    path_clip.addRoundedRect(QRectF(0, 0, size, size), 4, 4)
    painter.setClipPath(path_clip)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result


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
    edit_requested = Signal(str)  # key — opens CategoryEditPanel, only via the ⋮ menu (show_menu=True)
    reorder_requested = Signal(str, str)  # source_key, target_key — dropped source onto this row

    # Manhattan-length threshold before a press-drag becomes an actual
    # QDrag — same value/reasoning as TerrainCard's drag start (terrain_
    # card.py), just without that card's border-only drag zone: rows are
    # small and don't need a separate "click vs drag" region, only a
    # "did the mouse actually move" one.
    _DRAG_THRESHOLD = 10

    def __init__(self, key: str, icon: str, label: str, parent=None, show_menu: bool = False,
                 border_color: str = "", image_path: str = ""):
        super().__init__(parent)
        self.key = key
        self._selected = False
        self._border_color = border_color
        self._drag_start_pos: QPoint | None = None
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Fixed, not left to sizeHint() — the emoji icon (📋/⭐/📁) pulls in
        # Windows' color-emoji font as a per-character fallback, and that
        # font's line metrics are wildly taller than the row's actual text,
        # so an auto sizeHint balloons this row to ~100px+ instead of its
        # intended ~30px on real Windows rendering (not reproducible with
        # the offscreen/test QPA platform, which doesn't do that fallback).
        self.setFixedHeight(30)
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
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        icon_lbl.setStyleSheet("font-size: 12px; background: transparent; border: none;")
        thumb = _rounded_thumbnail(image_path, 16) if image_path else None
        if thumb is not None:
            icon_lbl.setPixmap(thumb)
        else:
            icon_lbl.setText(icon)
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
            menu_btn.setToolTip("Mais opções")
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
            menu.addAction("🎨 Editar", lambda: self.edit_requested.emit(self.key))
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

    def _refresh_style(self, drop_target: bool = False):
        if drop_target:
            self.setStyleSheet(f"QFrame {{ background: rgba(79,195,247,0.15); border: 1px dashed {Colors.ACCENT}; border-radius: 6px; }}")
            return
        border = f"border: 1px solid {self._border_color};" if self._border_color else "border: none;"
        if self._selected:
            self.setStyleSheet(f"QFrame {{ background: {Colors.ACCENT_DIM}; {border} border-radius: 6px; }}")
            self._label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        else:
            self.setStyleSheet(f"QFrame {{ background: transparent; {border} border-radius: 6px; }}"
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
        # clicked now fires on release, not press — so a press-then-drag
        # (see mouseMoveEvent) doesn't also navigate into the row being
        # dragged before the drop even lands.
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None and
                (event.pos() - self._drag_start_pos).manhattanLength() > self._DRAG_THRESHOLD):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.key)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            self.clicked.emit(self.key)
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() and event.mimeData().text() != self.key:
            event.acceptProposedAction()
            self._refresh_style(drop_target=True)

    def dragLeaveEvent(self, event):
        self._refresh_style()

    def dropEvent(self, event: QDropEvent):
        source_key = event.mimeData().text()
        if source_key and source_key != self.key:
            event.acceptProposedAction()
            self.reorder_requested.emit(source_key, self.key)
        self._refresh_style()


# Moved to src/layouts/panels/shared/import_export_helpers.py (zero
# coupling to Mobs internals) so Items e Habilidades can reuse it too —
# kept as an alias here so every existing `from
# src.layouts.panels.mobs.panel_widgets import _DropZone` import keeps
# working unchanged.
from src.layouts.panels.shared.import_export_helpers import DropZone as _DropZone  # noqa: E402


class _ClickableHeader(QFrame):
    """A header row that toggles something on click — same "real subclass
    with mousePressEvent as an actual method" requirement as
    CollapsibleSection's _SectionHeader (src/layouts/panels/
    collapsible_section.py): assigning to `.mousePressEvent` on a stock
    QFrame() instance isn't reliably picked up by Qt's virtual dispatch."""

    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class _SummaryCard(QFrame):
    """"Resumo Rápido" card — hides its legend (keeping just the donut)
    once there isn't enough height to show both without the legend's
    fixed-size rows overlapping the donut, instead of forcing a floor
    size to guarantee they always fit. On top of that automatic shrink,
    set_collapsed() lets the user manually fold the whole donut+legend
    body away entirely (see panel_data_mixin.py's header/arrow toggle),
    leaving just the "RESUMO RÁPIDO" title row — freeing that space for
    CATEGORIAS above it to grow into (see _build_left_column's 2:1
    stretch), same "responsive between the two" behavior the un-collapsed
    2:1 split already had, just re-proportioned around whichever amount
    of this card is actually showing right now.

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
    _EXPANDED_SIZE = QSize(150, 140)
    # Just the header row + card margins — collapsed state's actual floor
    # AND ceiling (see set_collapsed's setMaximumHeight), so the 2:1
    # QVBoxLayout stretch (categorias : this card) hands every pixel this
    # card gives up straight to categorias instead of stretch alone still
    # pulling this card back up toward its 1/3 share.
    _COLLAPSED_H = 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self._legend_container: QWidget | None = None
        self._body: QWidget | None = None
        self._collapsed = False

    def set_legend_container(self, widget: QWidget):
        self._legend_container = widget

    def set_body(self, widget: QWidget):
        """The donut+legend container as one unit — hidden entirely while
        collapsed, distinct from set_legend_container's legend-only
        auto-hide (which still applies normally whenever the body IS
        visible, see resizeEvent)."""
        self._body = widget

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        if self._body is not None:
            self._body.setVisible(not collapsed)
        # The hard cap is what actually frees the space for categorias —
        # a shrunk sizeHint alone doesn't stop a stretch-factor widget
        # from still being pulled back up to fill its share of leftover
        # layout space (see class docstring).
        self.setMaximumHeight(self._COLLAPSED_H if collapsed else 16777215)
        self.updateGeometry()

    def is_collapsed(self) -> bool:
        return self._collapsed

    def minimumSizeHint(self):
        return QSize(self._EXPANDED_SIZE.width(), self._COLLAPSED_H) if self._collapsed else self._EXPANDED_SIZE

    def sizeHint(self):
        return self.minimumSizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._collapsed and self._legend_container is not None:
            self._legend_container.setVisible(self.height() >= self._LEGEND_MIN_CARD_H)
