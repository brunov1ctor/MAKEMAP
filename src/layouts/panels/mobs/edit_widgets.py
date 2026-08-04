"""Standalone widget classes used inside MobEditPanel's sections — each is
"dumb"/signal-only (no calls back into MobEditPanel; every interaction goes
through a Qt signal MobEditPanel connects after construction), so they live
here instead of inline in mob_edit_panel.py.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget, QMenu, QScrollArea,
    QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRectF, QEventLoop, QTimer
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QPainter, QPainterPath, QIcon

from src.styles.tokens import Colors
from src.layouts.panels.mobs.categories import item_rarity_color
from src.layouts.panels.mobs.edit_helpers import _rarity_chip_label
from src.layouts.panels.brush.flow_layout import FlowLayout
from src.layouts.panel_manager import paint_glass_panel


class _DropImageButton(QToolButton):
    """The Visão Geral portrait button — click to browse (existing
    behavior, wired by OverviewSectionMixin) plus drag-and-drop of an image
    file straight from Explorer/Finder, same idea as the Importar _DropZone
    (panel_widgets.py) but sized/shaped as the portrait thumbnail itself
    rather than a standalone big drop target."""

    image_dropped = Signal(str)  # local file path

    _ACCEPTED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._cover_pixmap: QPixmap | None = None

    def set_cover_pixmap(self, pixmap: QPixmap | None):
        # QIcon on a QToolButton gets centered inside the style's own
        # button margin (QStyle::PM_ButtonMargin) even when iconSize
        # matches the widget size, so a pixmap pre-scaled to fit the
        # button still rendered with a visible gap around it. Painting it
        # directly over the full widget rect — the same trick already
        # used for MobCard's _CoverImageLabel — bypasses that margin.
        self._cover_pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self.setIcon(QIcon())
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._cover_pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(path)
        # Contain-fit (whole image visible, letterboxed) — not cover-fit,
        # which cropped tall/portrait images that didn't match the
        # button's own aspect ratio.
        scaled = self._cover_pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()

    def _first_accepted_path(self, mime_data) -> str | None:
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(self._ACCEPTED_SUFFIXES):
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and self._first_accepted_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        path = self._first_accepted_path(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.image_dropped.emit(path)
        else:
            event.ignore()


class _AssetDropScrollArea(QScrollArea):
    """The Assets list's own scroll area — accepts dragging asset files
    straight from Explorer/Finder onto it, same drag-and-drop idea as the
    Visão Geral portrait's _DropImageButton above, just multi-file and a
    broader set of extensions (3D models + textures, not only images)."""

    files_dropped = Signal(list)  # list[str] local file paths

    _ACCEPTED_SUFFIXES = (".fbx", ".obj", ".gltf", ".glb", ".png", ".jpg", ".jpeg", ".webp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._base_style = ""

    def set_base_style(self, style: str):
        """Stored so dragLeaveEvent/dropEvent can restore it after
        dragEnterEvent temporarily swaps in a highlighted border."""
        self._base_style = style
        self.setStyleSheet(style)

    def _accepted_paths(self, mime_data) -> list[str]:
        return [
            url.toLocalFile() for url in mime_data.urls()
            if url.toLocalFile().lower().endswith(self._ACCEPTED_SUFFIXES)
        ]

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and self._accepted_paths(event.mimeData()):
            event.acceptProposedAction()
            self.setStyleSheet(self._base_style + f"QScrollArea {{ border: 1px dashed {Colors.ACCENT}; }}")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._base_style)

    def dropEvent(self, event: QDropEvent):
        paths = self._accepted_paths(event.mimeData())
        self.setStyleSheet(self._base_style)
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            event.ignore()


class _CollapsibleSection(QFrame):
    """One of the edit panel's 3 top-level sections (Visão Geral /
    Atributos / Informações Extras) — a header button toggles its content
    visible/hidden, so a designer working only with, say, atributos can
    collapse the other two and reclaim vertical space instead of scrolling
    past them every time."""

    def __init__(self, title: str, content: QWidget, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 6px; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        self._title = title
        self._header_btn = QToolButton()
        self._header_btn.setCheckable(True)
        self._header_btn.setChecked(expanded)
        self._header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_PRIMARY};
                font-size: 10px; font-weight: bold; text-align: left; padding: 2px; }}
        """)
        self._header_btn.toggled.connect(self._on_toggled)
        outer.addWidget(self._header_btn)

        # Reparent BEFORE toggling visibility — `content` is a freshly
        # built QWidget() with no parent yet at this point, and calling
        # setVisible(True) on a still-parentless widget makes Qt treat it
        # as a real top-level window and briefly show it as one (a native
        # OS window flash) before the very next line reparents it into
        # this layout. addWidget() first means it already has a parent by
        # the time visibility is touched, so it's never shown as its own
        # window.
        outer.addWidget(content)
        content.setVisible(expanded)
        self._content = content
        self._refresh_header_text()

    def _on_toggled(self, checked: bool):
        self._content.setVisible(checked)
        self._refresh_header_text()

    def _refresh_header_text(self):
        arrow = "▾" if self._header_btn.isChecked() else "▸"
        self._header_btn.setText(f"{arrow} {self._title}")


class _DropTile(QFrame):
    """One square tile in Drops Principais — item icon + drop rate below
    it, matching the reference mock (no name text in the tile itself;
    the item name/qty show as a tooltip instead). Backed by a real Item
    row (self._uow.items) rather than a typed-in name, so the icon and
    future rarity/stat data all come from the same catalog every other
    "loot" reference in the app would use."""

    remove_requested = Signal(str)  # item_id
    open_requested = Signal(str)  # item_id — click anywhere on the tile except "✕"

    # SIZE used to be the tile's own OUTER width, with the thumbnail's edge
    # computed as `size - 40` — that "40" was really just the height
    # overhead from the remove-button row + pct label, wrongly reapplied to
    # shrink the (square) thumb's WIDTH too, leaving ~40px of pure empty
    # border down each side with nothing in it. SIZE is now the thumbnail's
    # own edge length directly (52 — unchanged from what it visually was
    # before, so images don't get smaller), and the tile's outer box is
    # sized tightly around it (thumb + small margins), not the other way
    # around — that's what actually shrinks the wasted chrome and lets
    # more tiles fit per row.
    SIZE = 52
    _MARGIN = 4

    def __init__(self, item: dict, rate: float, qty: int, parent=None, size: int | None = None, removable: bool = True):
        super().__init__(parent)
        self._item_id = item.get("id", "")
        thumb_h = size if size is not None else self.SIZE
        width = thumb_h + 2 * self._MARGIN
        # Remove-button row (15px + 2px spacing below it) only exists when
        # removable=True (Mobs edit panel) — Inspector's read-only tiles
        # (removable=False) skip it entirely, same as before.
        remove_row_h = 17 if removable else 0
        total_h = 2 * self._MARGIN + remove_row_h + thumb_h + 2 + 14  # margins + [remove row] + thumb + spacing + pct label
        self.setFixedSize(width, total_h)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(self._MARGIN, self._MARGIN, self._MARGIN, self._MARGIN)
        lay.setSpacing(2)

        # Inspector (map-panel quick view) shows the same tile read-only —
        # removal only ever happens from the Mobs edit panel's own Drops
        # Principais list, so it passes removable=False to skip this row
        # entirely instead of showing a "✕" that does nothing.
        if removable:
            top_row = QHBoxLayout()
            top_row.addStretch()
            remove_btn = QToolButton()
            remove_btn.setText("✕")
            remove_btn.setFixedSize(15, 15)
            remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_btn.setToolTip("Remover")
            remove_btn.setStyleSheet(f"""
                QToolButton {{ border: none; background: rgba(0,0,0,0.45); color: {Colors.TEXT_SECONDARY}; font-size: 9px; border-radius: 7px; }}
                QToolButton:hover {{ background: {Colors.ERROR}; color: white; }}
                QToolTip {{
                    background-color: {Colors.BG_ELEVATED};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 8px;
                    padding: 6px 10px;
                    font-size: 11px;
                }}
            """)
            remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._item_id))
            top_row.addWidget(remove_btn)
            lay.addLayout(top_row)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Square target box (thumb_h × thumb_h), not (size-16 × thumb_h) —
        # that used to be a ~76×52 landscape box, and KeepAspectRatioByExpanding
        # crops whatever overflows the target on the longer axis to "cover"
        # it. Against a square icon (the common case) that meant scaling
        # to a 76×76 square and then slicing 12px off the top AND bottom to
        # force it into 52px of height, for no visual gain — a square box
        # crops a square source not at all, and a non-square one only by
        # however much its own aspect ratio actually demands.
        thumb.setFixedSize(thumb_h, thumb_h)
        image_path = item.get("image_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(
                thumb_h, thumb_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            thumb.setText(item.get("icon") or "🎁")
            thumb.setStyleSheet("font-size: 26px; background: transparent; border: none;")
        lay.addWidget(thumb, 0, Qt.AlignmentFlag.AlignHCenter)

        pct = QLabel(f"{rate:.0f}%" if float(rate).is_integer() else f"{rate:.1f}%")
        pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pct.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(pct)

        name = item.get("name") or "Item removido do catálogo"
        self.setToolTip(f"{name} — {qty}x")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        # The "✕" is a real child QToolButton — Qt routes a click on it
        # straight to the button's own mousePressEvent (it never reaches
        # here), so this only ever fires for the rest of the tile, same as
        # _CatalogTile's own click handling.
        if event.button() == Qt.MouseButton.LeftButton and self._item_id:
            self.open_requested.emit(self._item_id)
        super().mousePressEvent(event)


class _AbilityTile(QFrame):
    """One square tile in Habilidades — same tile shape as _DropTile above
    (icon + a short caption below, "✕" to unlink) instead of the wider
    info card this used to be. Editing a skill's own name/description/
    rarity happens in the Habilidades catalog panel itself, not here, so
    this tile only needs to show what's linked to this mob and let the
    designer unlink it — no "..." menu, no inline edit. `skill` is the
    resolved catalog row (or a placeholder dict with an empty id when the
    link is broken/unmatched — see ExtrasSectionMixin._resolve_ability);
    `unlinked` flags that case by muting the caption instead of silently
    rendering it as a normal entry."""

    remove_requested = Signal(int)  # index into ExtrasSectionMixin._abilities
    open_requested = Signal(str)  # skill catalog id — click anywhere on the tile except "✕"

    # See _DropTile's own SIZE comment — same fix, same reasoning: this used
    # to be the tile's OUTER width (92) with the thumb computed as
    # `size - 40`, wasting ~40px of empty border around a 52px icon. SIZE is
    # now the thumbnail's own edge length directly (unchanged visual size),
    # and the box is sized tightly around it instead.
    SIZE = 52
    _MARGIN = 4

    def __init__(self, index: int, skill: dict, unlinked: bool = False, parent=None):
        super().__init__(parent)
        self._index = index
        self._skill_id = skill.get("id", "")
        thumb_h = self.SIZE
        width = thumb_h + 2 * self._MARGIN
        remove_row_h = 17  # button(15) + spacing(2) — always present here (unlike _DropTile, no removable=False caller)
        total_h = 2 * self._MARGIN + remove_row_h + thumb_h + 2 + 14  # margins + remove row + thumb + spacing + name label
        self.setFixedSize(width, total_h)
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.04); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(self._MARGIN, self._MARGIN, self._MARGIN, self._MARGIN)
        lay.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.addStretch()
        remove_btn = QToolButton()
        remove_btn.setText("✕")
        remove_btn.setFixedSize(15, 15)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setToolTip("Remover")
        remove_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: rgba(0,0,0,0.45); color: {Colors.TEXT_SECONDARY}; font-size: 9px; border-radius: 7px; }}
            QToolButton:hover {{ background: {Colors.ERROR}; color: white; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._index))
        top_row.addWidget(remove_btn)
        lay.addLayout(top_row)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Square target box — see the matching comment in _DropTile; a
        # non-square (size-16 × thumb_h) box cropped square source icons
        # top-and-bottom for no reason.
        thumb.setFixedSize(thumb_h, thumb_h)
        # Mirrors _DropTile's image-then-icon fallback exactly — image_path
        # already arrives resolved to an absolute path (see
        # panel_data_mixin.py's set_skills_catalog call).
        image_path = skill.get("image_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(
                thumb_h, thumb_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            thumb.setText(skill.get("icon") or "✨")
            thumb.setStyleSheet("font-size: 26px; background: transparent; border: none;")
        lay.addWidget(thumb, 0, Qt.AlignmentFlag.AlignHCenter)

        name_lbl = QLabel(skill.get("name") or "Habilidade removida")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_color = Colors.TEXT_MUTED if unlinked else Colors.TEXT_PRIMARY
        name_style = "font-style: italic;" if unlinked else "font-weight: bold;"
        name_lbl.setStyleSheet(f"color: {name_color}; font-size: 9px; {name_style} background: transparent; border: none;")
        lay.addWidget(name_lbl)

        tooltip = skill.get("name") or "Habilidade removida do catálogo"
        self.setToolTip(f"{tooltip} (não vinculado)" if unlinked else tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        # Same reasoning as _DropTile's own override — "✕" is a real child
        # QToolButton, Qt never routes its clicks here.
        if event.button() == Qt.MouseButton.LeftButton and self._skill_id:
            self.open_requested.emit(self._skill_id)
        super().mousePressEvent(event)


class _CatalogTile(QFrame):
    """One clickable square in a _CatalogSearchGrid — an Item/Skill catalog
    entry shown as image (or emoji fallback) + name, matching the reference
    mock: click adds it straight to the mob, no separate confirm step."""

    clicked = Signal(str)  # catalog id

    SIZE = 64

    def __init__(self, entry: dict, parent=None, size: int | None = None):
        super().__init__(parent)
        self._id = entry.get("id", "")
        size = size if size is not None else self.SIZE
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(size + 16)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.setToolTip(entry.get("name") or "")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        color = item_rarity_color(entry.get("rarity", "common"))
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(size, size)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_path = entry.get("image_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            icon_lbl.setPixmap(pixmap.scaled(
                size - 10, size - 10,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
            icon_lbl.setStyleSheet(
                f"background: rgba(255,255,255,0.05); border: 1px solid {color}88; border-radius: 10px;"
            )
        else:
            icon_lbl.setText(entry.get("icon") or "❔")
            icon_lbl.setStyleSheet(
                f"font-size: 24px; border-radius: 10px; border: 1px solid {color}88; "
                f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {color}33, stop:1 rgba(0,0,0,0.25));"
            )
        lay.addWidget(icon_lbl)

        name_lbl = QLabel(entry.get("name") or "")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        name_lbl.setWordWrap(True)
        name_lbl.setFixedWidth(size + 8)
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 9px; background: transparent; border: none;")
        lay.addWidget(name_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._id)
        super().mousePressEvent(event)


class _CatalogSearchGrid(QWidget):
    """Search box + wrapping grid of _CatalogTile — 'pesquisa que pega as
    criadas e mostra um grid' picker shared by Drops Principais and
    Habilidades (see ExtrasSectionMixin) instead of a QComboBox: type to
    filter the real Item/Skill catalog, click a tile to add it straight to
    the mob. Grows with its results between _MIN_H/_MAX_H, same idea as
    ExtrasSectionMixin._resize_scroll_to_content."""

    item_picked = Signal(str)  # catalog id

    _MIN_H = 108
    _MAX_H = 220

    def __init__(self, placeholder: str, parent=None, max_h: int | None = None, fill: bool = False):
        super().__init__(parent)
        self._catalog: list[dict] = []
        # Popup-context callers (see _CatalogPickerDialog) pass a taller
        # cap than the inline _MAX_H=220 — that limit was tuned for sitting
        # embedded in the Mob edit panel, not for being the only content of
        # a dedicated dialog.
        self._max_h = max_h if max_h is not None else self._MAX_H
        # fill=True (the dialog's own usage) drops the content-driven
        # clamped height entirely — the grid instead stretches to whatever
        # space the surrounding card's layout gives it (see
        # _CatalogPickerDialog, which now sizes that card to the popup's
        # full backdrop). Without this the grid stayed a small
        # fixed-height strip even though the card around it had grown,
        # reading as "a little panel floating inside a bigger one".
        self._fill = fill

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(f"🔍 {placeholder}")
        self._search_edit.textChanged.connect(lambda _t: self._refresh())
        outer.addWidget(self._search_edit)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        if self._fill:
            self._scroll.setMinimumHeight(self._MIN_H)
            self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self._scroll.setFixedHeight(self._MIN_H)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Colors.TEXT_MUTED}; border-radius: 2px; min-height: 20px; }}
        """)
        self._grid_widget = QWidget()
        self._grid = FlowLayout(self._grid_widget, spacing=10)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._scroll.setWidget(self._grid_widget)
        outer.addWidget(self._scroll)

        self._empty_lbl = QLabel("Nenhum resultado.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        self._empty_lbl.hide()
        outer.addWidget(self._empty_lbl)

    def set_catalog(self, entries: list[dict]):
        self._catalog = entries
        self._refresh()

    def _refresh(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self._search_edit.text().strip().lower()
        matches = [e for e in self._catalog if not query or query in (e.get("name") or "").lower()]
        for entry in matches:
            tile = _CatalogTile(entry)
            tile.clicked.connect(self.item_picked.emit)
            self._grid.addWidget(tile)
        self._empty_lbl.setVisible(not matches)
        if not self._fill:
            self._grid_widget.adjustSize()
            content_h = self._grid_widget.sizeHint().height()
            self._scroll.setFixedHeight(max(self._MIN_H, min(content_h, self._max_h)))


class _GlassCard(QFrame):
    """A QFrame painted with the project's shared frosted-glass look (see
    panel_manager.paint_glass_panel — the same one MobEditPanel itself
    paints its own background with) instead of a flat stylesheet color, so
    the popup card matches the rest of the app's look."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        paint_glass_panel(self, radius=12)


class _CatalogPickerDialog(QWidget):
    """Popup opened by the "+ Novo Item"/"+ Vincular Habilidade" buttons
    (see ExtrasSectionMixin) — the searchable card grid used to live inline
    in the Mob edit panel; it now only exists inside this popup, opened on
    demand instead of always taking up space.

    A plain child QWidget (semi-transparent backdrop + a glass card filling
    most of it) rather than a QDialog — QDialog spawns a real separate
    OS-level window (own title bar, own taskbar entry, movable independent
    of the app), which read as "outside the app" instead of an in-app
    popup. Scoped to `parent` itself — callers pass the sections scroll
    area's viewport (see ExtrasSectionMixin), not the whole Mob edit panel
    (header + footer included) — centering on the full panel instead of
    just the visible content band left the card floating disconnected from
    whichever section actually opened it whenever Visão Geral/Atributos
    pushed Informações Extras down. Runs a local QEventLoop to keep
    blocking the caller like `.exec()` used to.

    Construct with `parent` = the widget to scope the popup to, call
    `.exec()`, then read `picked_id` — stays None on Cancelar, the "✕"
    corner button, or a click on the backdrop outside the card."""

    _MARGIN = 28  # how much of the backdrop shows around the card

    def __init__(self, title: str, placeholder: str, catalog: list[dict], parent=None):
        super().__init__(parent)
        self.picked_id: str | None = None
        self._loop: QEventLoop | None = None
        # A plain QWidget doesn't paint its stylesheet's `background`
        # without this — without it the dark backdrop below was never
        # actually drawn, so only the card rendered, floating with nothing
        # behind it (looked like a separate window instead of a scrim over
        # the panel).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,0.55);")

        card = _GlassCard(self)
        card.setMinimumSize(320, 360)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(18, 16, 18, 16)
        card_lay.setSpacing(10)

        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        header.addWidget(title_lbl)
        header.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Fechar")
        close_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_MUTED}; font-size: 12px; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        close_btn.clicked.connect(self._cancel)
        header.addWidget(close_btn)
        card_lay.addLayout(header)

        self._grid = _CatalogSearchGrid(placeholder, fill=True)
        self._grid.set_catalog(catalog)
        self._grid.item_picked.connect(self._on_pick)
        # Stretch factor 1 — fill=True above drops the grid's own
        # content-driven clamped height, so it now needs this to actually
        # claim the space `card` has available instead of collapsing to
        # its minimum.
        card_lay.addWidget(self._grid, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(255,255,255,0.06); color: {Colors.TEXT_SECONDARY}; border: none;
                border-radius: 6px; padding: 5px 12px; font-size: 10px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.12); }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        card_lay.addLayout(btn_row)

        # `card` now fills the whole backdrop minus a fixed margin on every
        # side — it used to be sized to its own content and centered with
        # an addStretch() pair, which left a visible band of backdrop above
        # and below it, reading as a small floating panel nested inside the
        # bigger dimmed one instead of actually occupying it.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._MARGIN, self._MARGIN, self._MARGIN, self._MARGIN)
        outer.addWidget(card)

    def mousePressEvent(self, event):
        # Clicks land here only when they miss `card` (its children
        # consume their own clicks first) — i.e. a click on the backdrop.
        self._cancel()

    def _on_pick(self, catalog_id: str):
        self.picked_id = catalog_id
        self._close()

    def _cancel(self):
        self._close()

    def _close(self):
        if self._loop is not None:
            self._loop.quit()
        self.hide()
        # deleteLater instead of an immediate delete — `picked_id` still
        # needs to be readable by the caller right after exec() returns,
        # in the same call stack this schedules from.
        QTimer.singleShot(0, self.deleteLater)

    def exec(self) -> str | None:
        host = self.parentWidget()
        if host is not None:
            self.setGeometry(host.rect())
        self.show()
        self.raise_()
        self._loop = QEventLoop()
        self._loop.exec()
        return self.picked_id


class _AssetCard(QFrame):
    """One mob_assets row — a stamp file attached to this mob (see
    migration 8's docstring: the eventual canvas "Mobs" placement tool
    will stamp one of these). Same wide-row shape the old _AbilityCard
    used before Habilidades switched to a square-tile grid (see
    _AbilityTile)."""

    delete_requested = Signal(str)  # asset id

    def __init__(self, asset: dict, parent=None):
        super().__init__(parent)
        self._asset_id = asset.get("id", "")
        self.setStyleSheet(f"""
            QFrame {{ background: rgba(255,255,255,0.03); border: 1px solid {Colors.BORDER_SUBTLE}; border-radius: 8px; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)

        color = item_rarity_color(asset.get("rarity", "common"))
        thumb = QLabel()
        thumb.setFixedSize(64, 64)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_path = asset.get("file_path") or ""
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            thumb.setText("🗿")
            thumb.setStyleSheet(
                f"font-size: 24px; border-radius: 6px; border: 1px solid {color}88; "
                f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {color}33, stop:1 rgba(0,0,0,0.25));"
            )
        row.addWidget(thumb)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        name_lbl = QLabel(asset.get("name") or "Sem nome")
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        mid.addWidget(name_lbl)
        size_bytes = asset.get("file_size") or 0
        size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        type_lbl = QLabel(asset.get("asset_type") or "Arquivo")
        type_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; background: transparent; border: none;")
        meta_row.addWidget(type_lbl)
        size_lbl = QLabel(f"{size_mb:.1f} MB" if size_mb else "")
        size_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        meta_row.addWidget(size_lbl)
        meta_row.addStretch()
        mid.addLayout(meta_row)
        row.addLayout(mid, 1)

        side = QVBoxLayout()
        side.setSpacing(4)
        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(_rarity_chip_label(asset.get("rarity", "common")))
        side.addLayout(top)
        menu_row = QHBoxLayout()
        menu_row.addStretch()
        menu_btn = QToolButton()
        menu_btn.setText("⋯")
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_btn.setToolTip("Mais opções")
        menu_btn.setStyleSheet(f"""
            QToolButton {{ border: none; background: transparent; color: {Colors.TEXT_SECONDARY}; font-size: 13px; font-weight: bold; }}
            QToolButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
            QToolButton::menu-indicator {{ image: none; }}
            QToolTip {{
                background-color: {Colors.BG_ELEVATED};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 11px;
            }}
        """)
        menu = QMenu(menu_btn)
        menu.setStyleSheet(f"""
            QMenu {{ background: {Colors.BG_ELEVATED}; color: {Colors.TEXT_PRIMARY}; border: 1px solid {Colors.BORDER}; padding: 4px; }}
            QMenu::item {{ padding: 4px 20px 4px 8px; border-radius: 3px; font-size: 10px; }}
            QMenu::item:selected {{ background: {Colors.ACCENT_DIM}; }}
        """)
        menu.addAction("🗑 Excluir", lambda: self.delete_requested.emit(self._asset_id))
        menu_btn.setMenu(menu)
        menu_row.addWidget(menu_btn)
        side.addLayout(menu_row)
        row.addLayout(side)
